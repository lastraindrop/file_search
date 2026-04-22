import pytest
from file_cortex_core import PathValidator

def test_golden_path_end_to_end(project_client, mock_project):
    """Scenario: Full workflow from project registration to context export.
    
    Covers: Open -> Search -> Metadata -> Staging -> Stats -> XML Generate.
    """
    path = str(mock_project)
    
    # 1. Register/Open Workspace
    res_open = project_client.post("/api/open", json={"path": path})
    assert res_open.status_code == 200
    norm_path = PathValidator.norm_path(path)
    assert res_open.json()["path"] == norm_path
    
    # 2. Search for a file
    # We use WebSocket search simulation (direct call if possible or http fallback)
    # Here we check if the workspace is actually registered by listing children
    res_children = project_client.post("/api/fs/children", json={"path": path})
    assert res_children.status_code == 200
    children = res_children.json()["children"]
    assert len(children) > 0
    
    # 3. Add a note to a file
    target_file = str(mock_project / "src" / "main.py")
    res_note = project_client.post("/api/project/note", json={
        "project_path": path,
        "file_path": target_file,
        "note": "Initial script"
    })
    assert res_note.status_code == 200
    
    # 4. Stage files (Bulk Stage)
    res_stage = project_client.post("/api/project/settings", json={
        "project_path": path,
        "settings": {"staging_list": [target_file]}
    })
    assert res_stage.status_code == 200
    
    # 5. Check Token Stats
    res_stats = project_client.post("/api/project/stats", json={
        "paths": [target_file],
        "project_path": path
    })
    assert res_stats.status_code == 200
    assert res_stats.json()["total_tokens"] > 0
    
    # 6. Generate XML Context with Blueprint
    res_gen = project_client.post("/api/generate", json={
        "files": [target_file],
        "project_path": path,
        "export_format": "xml",
        "include_blueprint": True
    })
    assert res_gen.status_code == 200
    content = res_gen.json()["content"]
    assert "<blueprint>" in content
    assert "<context>" in content
    assert "main.py" in content
    assert "Initial script" not in content # Notes are for user, not usually context unless specified

def test_parameter_combination_security_stress(project_client, mock_project, system_dir):
    """Verify that multiple valid/invalid parameter combinations don't leak access."""
    # Attempt to generate context for a system file using a registered project as 'root'
    # This checks if PathValidator is properly integrated in the generate endpoint.
    root = str(mock_project)
    # Target a sensitive path outside the root
    evil_path = system_dir + "/test.txt"
    
    res = project_client.post("/api/generate", json={
        "files": [evil_path],
        "project_path": root,
        "export_format": "xml"
    })
    
    # It should succeed but return an empty context because evil_path is unsafe
    assert res.status_code == 200
    assert "<file" not in res.json()["content"]
