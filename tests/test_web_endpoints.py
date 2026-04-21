
def test_open_nonexistent_project(api_client):
    """Verify 404/400 for invalid project paths."""
    res = api_client.post("/api/open", json={"path": "/this/path/does/not/exist/at/all/fc_test_12345"})
    assert res.status_code in (404, 400)

def test_open_system_dir_blocked(api_client, system_dir):
    """Verify security block for system directories."""
    res = api_client.post("/api/open", json={"path": system_dir})
    # PathValidator.validate_project raises HTTPException 400 or 403
    assert res.status_code in (400, 403)

def test_content_unauthorized_path(api_client, tmp_path):
    """Accessing content of a file outside registered project roots should fail."""
    f = tmp_path / "secret.txt"
    f.write_text("unauthorized")
    res = api_client.get(f"/api/content?path={str(f)}")
    assert res.status_code == 403

def test_children_unauthorized_path(api_client, tmp_path):
    """Directory listing outside registered project roots should fail."""
    res = api_client.post("/api/fs/children", json={"path": str(tmp_path)})
    assert res.status_code == 403

def test_save_oversized_content(project_client, mock_project):
    """Test the 10MB Pydantic limit (or close to it)."""
    target = str(mock_project / "large.txt")
    # Pydantic max_length is 10,000,000
    huge_data = "X" * 10_000_001
    res = project_client.post("/api/fs/save", json={"path": target, "content": huge_data})
    assert res.status_code == 422 # Validation Error

def test_stage_all_excludes(project_client, mock_project):
    """Verify that stage_all respects exclusion settings."""
    root = str(mock_project)
    # 1. Set exclude in project settings
    # Using 'src*' to reliably match the src directory in the manual exclude logic (fnmatch)
    project_client.post("/api/project/settings", json={
        "project_path": root,
        "settings": {"excludes": "src*"}
    })

    # 2. Stage All
    res = project_client.post("/api/actions/stage_all", json={
        "project_path": root,
        "mode": "files",
        "apply_excludes": True
    })
    assert res.status_code == 200
    # src/main.py should be excluded
    data = project_client.get(f"/api/project/config?path={root}").json()
    staging = data.get("staging_list", [])
    assert not any("src" in p for p in staging)

def test_global_settings_roundtrip(api_client):
    """Verify global settings persistence through API."""
    new_settings = {
        "preview_limit_mb": 5.5,
        "token_threshold": 500000,
        "theme": "dark"
    }
    api_client.post("/api/config/global", json=new_settings)

    res = api_client.get("/api/config/global")
    data = res.json()
    assert data["preview_limit_mb"] == 5.5
    assert data["theme"] == "dark"

def test_workspaces_pin_toggle(api_client, mock_project):
    """Verify pin toggling and summary reflection."""
    path = str(mock_project)
    # Register first
    api_client.post("/api/open", json={"path": path})

    # Toggle Pin
    res = api_client.post("/api/workspaces/pin", json={"path": path})
    assert res.json()["is_pinned"] is True

    # Verify in workspaces list
    summary = api_client.get("/api/workspaces").json()
    from file_cortex_core import PathValidator
    norm_path = PathValidator.norm_path(path)
    assert any(PathValidator.norm_path(p["path"]) == norm_path for p in summary["pinned"])

def test_project_note_and_tag(project_client, mock_project):
    """Verify note and tag CRUD."""
    root = str(mock_project)
    f = str(mock_project / "src" / "main.py")

    # 1. Add Note
    project_client.post("/api/project/note", json={
        "project_path": root, "file_path": f, "note": "Refactor needed"
    })

    # 2. Add Tag
    project_client.post("/api/project/tag", json={
        "project_path": root, "file_path": f, "tag": "Priority", "action": "add"
    })

    # 3. Verify in config
    config = project_client.get(f"/api/project/config?path={root}").json()
    from file_cortex_core import PathValidator
    f_norm = PathValidator.norm_path(f)
    notes = config.get("notes", {})
    assert any(PathValidator.norm_path(k) == f_norm and v == "Refactor needed"
               for k, v in notes.items()), f"Note not found. Keys: {list(notes.keys())}, Expected: {f_norm}"
    tags = config.get("tags", {})
    assert any(PathValidator.norm_path(k) == f_norm and "Priority" in v
               for k, v in tags.items()), f"Tag not found. Keys: {list(tags.keys())}, Expected: {f_norm}"
