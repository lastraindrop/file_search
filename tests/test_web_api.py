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

# --- Workspace Memory API Tests ---

def test_workspace_memory_endpoints(mock_project):
    # 1. Open
    client.post("/api/open", json={"path": str(mock_project)})
    
    # 2. Add Note
    test_file = str(mock_project / "src" / "main.py")
    res = client.post("/api/project/note", json={
        "project_path": str(mock_project),
        "file_path": test_file,
        "note": "Entry point"
    })
    assert res.status_code == 200
    
    # 3. Add Tag
    res = client.post("/api/project/tag", json={
        "project_path": str(mock_project),
        "file_path": test_file,
        "tag": "v1",
        "action": "add"
    })
    assert res.status_code == 200
    
    # 4. Verify Config
    res = client.get(f"/api/project/config?path={str(mock_project)}")
    data = res.json()
    assert data["notes"][test_file] == "Entry point"
    assert "v1" in data["tags"][test_file]

def test_recent_projects_api(mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    res = client.get("/api/recent_projects")
    assert any(p["path"] == str(mock_project) for p in res.json())

# --- Advanced File Ops API Tests ---

def test_fs_create_archive_api(mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    
    # Create File
    res = client.post("/api/fs/create", json={
        "parent_path": str(mock_project),
        "name": "api_test.txt"
    })
    assert res.status_code == 200
    assert os.path.exists(mock_project / "api_test.txt")
    
    # Archive
    res = client.post("/api/fs/archive", json={
        "paths": [str(mock_project / "api_test.txt")],
        "output_name": "api_archive.zip",
        "project_root": str(mock_project)
    })
    assert res.status_code == 200
    assert os.path.exists(mock_project / "api_archive.zip")

def test_fs_ops_safety_advanced(mock_project):
    """Ensure advanced operations are also jailed to project root."""
    client.post("/api/open", json={"path": str(mock_project)})
    
    # Try to create outside
    res = client.post("/api/fs/create", json={
        "parent_path": "C:/Windows",
        "name": "evil.txt"
    })
    assert res.status_code == 403
    
    # Try to archive outside
    res = client.post("/api/fs/archive", json={
        "paths": ["C:/Windows/system.ini"],
        "output_name": "stolen.zip",
        "project_root": str(mock_project)
    })
    assert res.status_code == 403

def test_project_settings_persistence(mock_project):
    proj_path = str(mock_project)
    # Open project first to register it
    client.post("/api/open", json={"path": proj_path})
    
    # Update settings
    new_excludes = "*.tmp *.bak"
    res = client.post("/api/project/settings", json={
        "project_path": proj_path,
        "settings": {"excludes": new_excludes}
    })
    assert res.status_code == 200
    
    # Verify settings are persisted in config
    res = client.get(f"/api/project/config?path={proj_path}")
    assert res.status_code == 200
    assert res.json()["excludes"] == new_excludes

def test_get_valid_project_root_logic(mock_project):
    """Directly tests the helper logic for project root resolution."""
    from web_app import get_valid_project_root, data_mgr
    
    p1 = str(mock_project)
    data_mgr.data["projects"][p1] = {"excludes": ""}
    
    # Subpath should resolve to p1
    assert get_valid_project_root(str(mock_project / "src")) == p1
    # Deep subpath should resolve to p1
    assert get_valid_project_root(str(mock_project / "src" / "main.py")) == p1
    # Outside path should not resolve
    assert get_valid_project_root("C:/Windows") is None

def test_multi_project_isolation():
    """Verify that a path is only valid if it belongs to its registered project."""
    import tempfile
    import shutil
    tmp_dir = tempfile.mkdtemp()
    tmp_path = pathlib.Path(tmp_dir)
    try:
        proj_a = tmp_path / "proj_a"
        proj_a.mkdir()
        (proj_a / "a.txt").touch()
        
        proj_b = tmp_path / "proj_b"
        proj_b.mkdir()
        (proj_b / "b.txt").touch()
        
        # Register both
        client.post("/api/open", json={"path": str(proj_a)})
        client.post("/api/open", json={"path": str(proj_b)})
        
        # Access fine
        res = client.get(f"/api/content?path={str(proj_a / 'a.txt')}")
        assert res.status_code == 200
        
        # Access fine
        res = client.get(f"/api/content?path={str(proj_b / 'b.txt')}")
        assert res.status_code == 200
        
        # Fake a path that looks like its inside but isn't
        fake_path = str(tmp_path / "proj_c" / "c.txt")
        res = client.get(f"/api/content?path={fake_path}")
        assert res.status_code == 403
    finally:
        shutil.rmtree(tmp_dir)
