import pytest
import os
import pathlib
from fastapi.testclient import TestClient
from web_app import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def registered_client(client, mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    return client

def test_api_open_success(client, mock_project):
    res = client.post("/api/open", json={"path": str(mock_project)})
    assert res.status_code == 200
    assert "name" in res.json()

def test_api_open_invalid(client):
    # Cross-platform non-existent path
    non_existent = str(pathlib.Path("/NonExistentPath/123/456").resolve()) if os.name != 'nt' else "C:/NonExistentPath/123/456"
    res = client.post("/api/open", json={"path": non_existent})
    assert res.status_code == 404

from unittest.mock import patch

def test_api_open_system_dir_blocked(client):
    """Verify that system directories are rejected."""
    # Root directory
    root_dir = str(pathlib.Path(os.path.abspath(os.sep)).resolve())
    res = client.post("/api/open", json={"path": root_dir})
    assert res.status_code in (400, 403)

    # System directory (cross-platform blocked keywords)
    sys_dir = "C:/Windows" if os.name == 'nt' else "/etc"
    with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.is_dir", return_value=True):
        res = client.post("/api/open", json={"path": sys_dir})
        assert res.status_code == 400

def test_api_children_metadata(registered_client, mock_project):
    res = registered_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    children = res.json()["children"]
    for c in children:
        assert all(k in c for k in ("size", "mtime", "ext"))
        if c["type"] == "file" and c["name"] == "main.py":
            assert c["ext"] == ".py"

def test_api_security_path_traversal(registered_client, mock_project):
    """Critical: Verify that accessing paths outside project root returns 403."""
    unsafe_path = "C:/Windows/System32/drivers/etc/hosts" if os.name == 'nt' else "/etc/hosts"
    res = registered_client.get(f"/api/content?path={unsafe_path}")
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    traversal_path = str(mock_project / ".." / "some_other_file")
    res = registered_client.get(f"/api/content?path={traversal_path}")
    assert res.status_code == 403

def test_fs_ops_security(registered_client, mock_project):
    # Test rename with traversal in new_name (should be 400)
    res = registered_client.post("/api/fs/rename", json={
        "project_path": str(mock_project),
        "path": str(mock_project / "src" / "main.py"),
        "new_name": "../../hacker.py"
    })
    assert res.status_code == 400
    
    # Test rename with unsafe source path (should be 403)
    unsafe_path = "C:/Windows/system.ini" if os.name == 'nt' else "/etc/passwd"
    res = registered_client.post("/api/fs/rename", json={
        "project_path": str(mock_project),
        "path": unsafe_path,
        "new_name": "normal.py"
    })
    assert res.status_code == 403

def test_api_content_success(registered_client, mock_project):
    path = str(mock_project / "src" / "main.py")
    res = registered_client.get(f"/api/content?path={path}")
    assert res.status_code == 200
    assert "print" in res.json()["content"]

def test_websocket_search_basic(registered_client, mock_project):
    with registered_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        assert all(k in data for k in ("size", "mtime"))
        data = ws.receive_json()
        assert data["status"] == "DONE"

def test_workspace_memory_endpoints(registered_client, mock_project):
    test_file = str(mock_project / "src" / "main.py")
    res = registered_client.post("/api/project/note", json={
        "project_path": str(mock_project),
        "file_path": test_file,
        "note": "Entry point"
    })
    assert res.status_code == 200

    res = registered_client.post("/api/project/tag", json={
        "project_path": str(mock_project),
        "file_path": test_file,
        "tag": "v1",
        "action": "add"
    })
    assert res.status_code == 200

    res = registered_client.get(f"/api/project/config?path={str(mock_project)}")
    data = res.json()
    assert data["notes"][test_file] == "Entry point"
    assert "v1" in data["tags"][test_file]

def test_recent_projects_api(registered_client, mock_project):
    res = registered_client.get("/api/recent_projects")
    assert any(p["path"] == str(mock_project) for p in res.json())

def test_fs_create_archive_api(registered_client, mock_project):
    res = registered_client.post("/api/fs/create", json={
        "parent_path": str(mock_project),
        "name": "api_test.txt"
    })
    assert res.status_code == 200
    assert os.path.exists(mock_project / "api_test.txt")

    res = registered_client.post("/api/fs/archive", json={
        "paths": [str(mock_project / "api_test.txt")],
        "output_name": "api_archive.zip",
        "project_root": str(mock_project)
    })
    assert res.status_code == 200
    assert os.path.exists(mock_project / "api_archive.zip")

def test_fs_ops_safety_advanced(registered_client, mock_project):
    unsafe_dir = "C:/Windows" if os.name == 'nt' else "/etc"
    res = registered_client.post("/api/fs/create", json={
        "parent_path": unsafe_dir,
        "name": "evil.txt"
    })
    assert res.status_code == 403

    unsafe_p = "C:/Windows/system.ini" if os.name == 'nt' else "/etc/passwd"
    res = registered_client.post("/api/fs/archive", json={
        "paths": [unsafe_p],
        "output_name": "stolen.zip",
        "project_root": str(mock_project)
    })
    assert res.status_code == 403

def test_fs_move_safety_permutations(registered_client, mock_project):
    src = str(mock_project / "src" / "main.py")
    unsafe_dir = "C:/Windows" if os.name == 'nt' else "/etc"
    res = registered_client.post("/api/fs/move", json={
        "src_paths": [src],
        "dst_dir": unsafe_dir
    })
    assert res.status_code == 200
    assert res.json()["new_paths"] == []

def test_api_validation_errors(client):
    res = client.post("/api/open", json={})
    assert res.status_code == 422
    res = client.post("/api/generate", json={"files": "not-a-list"})
    assert res.status_code == 422

def test_save_content_no_project_access(client):
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    try:
        res = client.post("/api/fs/save", json={
            "path": temp_path,
            "content": "new content"
        })
        assert res.status_code == 403
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

def test_project_settings_persistence(registered_client, mock_project):
    proj_path = str(mock_project)
    new_excludes = "*.tmp *.bak"
    res = registered_client.post("/api/project/settings", json={
        "project_path": proj_path,
        "settings": {"excludes": new_excludes}
    })
    assert res.status_code == 200

    res = registered_client.get(f"/api/project/config?path={proj_path}")
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

def test_multi_project_isolation(client):
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

        client.post("/api/open", json={"path": str(proj_a)})
        client.post("/api/open", json={"path": str(proj_b)})

        res = client.get(f"/api/content?path={str(proj_a / 'a.txt')}")
        assert res.status_code == 200

        res = client.get(f"/api/content?path={str(proj_b / 'b.txt')}")
        assert res.status_code == 200

        fake_path = str(tmp_path / "proj_c" / "c.txt")
        res = client.get(f"/api/content?path={fake_path}")
        assert res.status_code == 403
    finally:
        shutil.rmtree(tmp_dir)
