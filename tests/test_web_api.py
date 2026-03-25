import pytest
import os
import pathlib
from fastapi.testclient import TestClient
from web_app import app

# Using global fixtures from conftest.py

def test_api_open_success(api_client, mock_project):
    res = api_client.post("/api/open", json={"path": str(mock_project)})
    assert res.status_code == 200
    assert "name" in res.json()

def test_api_open_invalid(api_client, system_dir):
    # Use system_dir + something clearly fake
    non_existent = os.path.join(system_dir, "NonExistentPath_XYZ_123")
    res = api_client.post("/api/open", json={"path": non_existent})
    assert res.status_code == 404

from unittest.mock import patch

def test_api_open_system_dir_blocked(api_client, system_dir):
    """Verify that system directories are rejected."""
    res = api_client.post("/api/open", json={"path": system_dir})
    assert res.status_code in (400, 403)

def test_api_children_metadata(project_client, mock_project):
    res = project_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    children = res.json()["children"]
    for c in children:
        assert all(k in c for k in ("size", "mtime", "ext", "mtime_fmt"))
        if c["type"] == "file" and c["name"] == "main.py":
            assert c["ext"] == ".py"
            # Verify date-like format (YYYY-MM-DD)
            assert "-" in c["mtime_fmt"]

def test_api_security_path_traversal(project_client, mock_project, system_dir):
    """Critical: Verify that accessing paths outside project root returns 403."""
    unsafe_path = os.path.join(system_dir, "drivers/etc/hosts") if os.name == 'nt' else "/etc/hosts"
    res = project_client.get(f"/api/content?path={unsafe_path}")
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    traversal_path = str(mock_project / ".." / "some_other_file")
    res = project_client.get(f"/api/content?path={traversal_path}")
    assert res.status_code == 403

def test_fs_ops_security(project_client, mock_project, system_dir):
    # Test rename with traversal in new_name (should be 400)
    res = project_client.post("/api/fs/rename", json={
        "project_path": str(mock_project),
        "path": str(mock_project / "src" / "main.py"),
        "new_name": "../../hacker.py"
    })
    assert res.status_code == 400
    
    # Test rename with unsafe source path (should be 403)
    res = project_client.post("/api/fs/rename", json={
        "project_path": str(mock_project),
        "path": os.path.join(system_dir, "system.ini"),
        "new_name": "normal.py"
    })
    assert res.status_code == 403

def test_api_content_success(project_client, mock_project):
    path = str(mock_project / "src" / "main.py")
    res = project_client.get(f"/api/content?path={path}")
    assert res.status_code == 200
    assert "print" in res.json()["content"]

def test_websocket_search_basic(project_client, mock_project):
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        assert all(k in data for k in ("size", "mtime"))
        data = ws.receive_json()
        assert data["status"] == "DONE"

def test_workspace_memory_endpoints(project_client, mock_project):
    test_file = str(mock_project / "src" / "main.py")
    res = project_client.post("/api/project/note", json={
        "project_path": str(mock_project),
        "file_path": test_file,
        "note": "Entry point"
    })
    assert res.status_code == 200

    res = project_client.post("/api/project/tag", json={
        "project_path": str(mock_project),
        "file_path": test_file,
        "tag": "v1",
        "action": "add"
    })
    assert res.status_code == 200

    res = project_client.get(f"/api/project/config?path={str(mock_project)}")
    data = res.json()
    assert data["notes"][test_file] == "Entry point"
    assert "v1" in data["tags"][test_file]

def test_recent_projects_api(project_client, mock_project):
    res = project_client.get("/api/recent_projects")
    assert any(p["path"] == str(mock_project) for p in res.json())

def test_fs_create_archive_api(project_client, mock_project):
    res = project_client.post("/api/fs/create", json={
        "parent_path": str(mock_project),
        "name": "api_test.txt"
    })
    assert res.status_code == 200
    assert os.path.exists(mock_project / "api_test.txt")

    res = project_client.post("/api/fs/archive", json={
        "paths": [str(mock_project / "api_test.txt")],
        "output_name": "api_archive.zip",
        "project_root": str(mock_project)
    })
    assert res.status_code == 200
    assert os.path.exists(mock_project / "api_archive.zip")

def test_fs_ops_safety_advanced(project_client, mock_project, system_dir):
    res = project_client.post("/api/fs/create", json={
        "parent_path": system_dir,
        "name": "evil.txt"
    })
    assert res.status_code == 403

    res = project_client.post("/api/fs/archive", json={
        "paths": [os.path.join(system_dir, "system.ini")],
        "output_name": "stolen.zip",
        "project_root": str(mock_project)
    })
    assert res.status_code == 403

def test_fs_move_safety_permutations(project_client, mock_project, system_dir):
    src = str(mock_project / "src" / "main.py")
    res = project_client.post("/api/fs/move", json={
        "src_paths": [src],
        "dst_dir": system_dir
    })
    assert res.status_code == 200
    assert res.json()["new_paths"] == []

def test_api_validation_errors(api_client):
    res = api_client.post("/api/open", json={})
    assert res.status_code == 422
    res = api_client.post("/api/generate", json={"files": "not-a-list"})
    assert res.status_code == 422

def test_save_content_no_project_access(api_client):
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    try:
        res = api_client.post("/api/fs/save", json={
            "path": temp_path,
            "content": "new content"
        })
        assert res.status_code == 403
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

def test_project_settings_persistence(project_client, mock_project):
    proj_path = str(mock_project)
    new_excludes = "*.tmp *.bak"
    res = project_client.post("/api/project/settings", json={
        "project_path": proj_path,
        "settings": {"excludes": new_excludes}
    })
    assert res.status_code == 200

    res = project_client.get(f"/api/project/config?path={proj_path}")
    assert res.status_code == 200
    assert res.json()["excludes"] == new_excludes

def test_get_valid_project_root_logic(mock_project):
    from web_app import get_valid_project_root, data_mgr
    p1 = str(mock_project)
    data_mgr.data["projects"][p1] = {"excludes": ""}

    assert get_valid_project_root(str(mock_project / "src")) == p1
    assert get_valid_project_root(str(mock_project / "src" / "main.py")) == p1
    unsafe_dir = "C:/Windows" if os.name == 'nt' else "/etc"
    assert get_valid_project_root(unsafe_dir) is None

@patch('web_app.logger')
def test_api_audit_logging(mock_logger, project_client, mock_project):
    """Verify that sensitive write operations trigger AUDIT logs."""
    test_file = str(mock_project / "src" / "main.py")
    
    # 1. Test Delete Audit
    project_client.post("/api/fs/delete", json={
        "project_path": str(mock_project),
        "paths": [test_file]
    })
    # Filter for AUDIT logs
    audit_calls = [c for c in mock_logger.info.call_args_list if "AUDIT" in str(c)]
    assert len(audit_calls) > 0
    assert "Deleting" in str(audit_calls[-1])
