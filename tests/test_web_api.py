import pytest
from fastapi.testclient import TestClient
from web_app import app
import os
import pathlib

client = TestClient(app)

def test_api_open_success(mock_project):
    res = client.post("/api/open", json={"path": str(mock_project)})
    assert res.status_code == 200
    assert "name" in res.json()

def test_api_open_invalid():
    res = client.post("/api/open", json={"path": "C:/NonExistentPath/123/456"})
    assert res.status_code == 404

def test_api_children_metadata(mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    res = client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    children = res.json()["children"]
    # Check if metadata fields exist
    for c in children:
        assert "size" in c
        assert "mtime" in c
        assert "ext" in c
        if c["type"] == "file" and c["name"] == "main.py":
            assert c["ext"] == ".py"

def test_api_security_path_traversal(mock_project):
    """Critical: Verify that accessing paths outside project root returns 403."""
    client.post("/api/open", json={"path": str(mock_project)})
    
    # Attempt to access a sensitive system path (simulated)
    unsafe_path = "C:/Windows/System32/drivers/etc/hosts"
    res = client.get(f"/api/content?path={unsafe_path}")
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]
    
    # Attempt relative traversal
    traversal_path = str(mock_project / ".." / "some_other_file")
    res = client.get(f"/api/content?path={traversal_path}")
    assert res.status_code == 403

def test_fs_ops_security(mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    
    # Rename across projects (Unsafe)
    res = client.post("/api/fs/rename", json={
        "path": str(mock_project / "src" / "main.py"),
        "new_name": "../../hacker.py"
    })
    assert res.status_code == 403

def test_api_content_success(mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    path = str(mock_project / "src" / "main.py")
    res = client.get(f"/api/content?path={path}")
    assert res.status_code == 200
    assert "print" in res.json()["content"]

def test_websocket_search_basic(mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    with client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        # First message should be a result
        data = ws.receive_json()
        assert "main.py" in data["name"]
        assert "size" in data
        assert "mtime" in data
        # Last message should be DONE
        data = ws.receive_json()
        assert data["status"] == "DONE"
