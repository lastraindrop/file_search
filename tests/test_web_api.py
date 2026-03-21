import pytest
from fastapi.testclient import TestClient
from web_app import app
import json

client = TestClient(app)

def test_api_open(mock_project):
    response = client.post("/api/open", json={"path": str(mock_project)})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["root"]["name"] == mock_project.name

def test_api_children(mock_project):
    # Use the project directory to test lazy loading
    response = client.post("/api/fs/children", json={"path": str(mock_project)})
    assert response.status_code == 200
    data = response.json()
    # Should contain 'src', '.gitignore', 'image.png' (if not ignored)
    names = [c["name"] for c in data["children"]]
    assert "src" in names
    assert ".gitignore" in names

def test_api_content(mock_project):
    file_path = str(mock_project / "src" / "main.py")
    response = client.get(f"/api/content?path={file_path}")
    assert response.status_code == 200
    assert "print('hello')" in response.json()["content"]

def test_api_generate(mock_project):
    files = [str(mock_project / "src" / "main.py"), str(mock_project / "src" / "utils.js")]
    response = client.post("/api/generate", json={"files": files})
    assert response.status_code == 200
    content = response.json()["content"]
    assert "File: main.py" in content
    assert "File: utils.js" in content

def test_fs_ops(mock_project):
    # Rename
    old_path = mock_project / "src" / "main.py"
    response = client.post("/api/fs/rename", json={"path": str(old_path), "new_name": "new_main.py"})
    assert response.status_code == 200
    assert (mock_project / "src" / "new_main.py").exists()
    
    # Move
    src = mock_project / "src" / "new_main.py"
    dst = mock_project
    response = client.post("/api/fs/move", json={"src_paths": [str(src)], "dst_dir": str(dst)})
    assert response.status_code == 200
    assert (mock_project / "new_main.py").exists()
    
    # Delete (Batch)
    paths = [str(mock_project / "new_main.py"), str(mock_project / "src" / "utils.js")]
    response = client.post("/api/fs/delete", json={"paths": paths})
    assert response.status_code == 200
    assert not (mock_project / "new_main.py").exists()
    assert not (mock_project / "src" / "utils.js").exists()
