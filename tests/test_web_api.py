import pytest
import os
import pathlib
import json
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient
from web_app import app
from file_cortex_core import ActionBridge, DataManager


def test_api_open_project(project_client, mock_project):
    """Verify project registration and initial node info."""
    res = project_client.post("/api/open", json={"path": str(mock_project)})
    assert res.status_code == 200
    data = res.json()
    assert "name" in data
    assert data["type"] == "dir"
    assert data["has_children"] is True

def test_api_get_children(project_client, mock_project):
    """Verify directory listing."""
    res = project_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    children = res.json()["children"]
    names = [c["name"] for c in children]
    assert "src" in names
    assert "config.json" in names

def test_api_search_websocket(project_client, mock_project):
    """Verify websocket search flow."""
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        # Collect all results until DONE
        results = []
        while True:
            data = ws.receive_json()
            if data.get("status") == "DONE":
                break
            results.append(data)
        
        assert len(results) >= 1
        assert any("main.py" in r["name"] for r in results)

def test_api_staging_workflow(project_client, mock_project):
    """Verify adding to staging via API."""
    proj_path = str(mock_project)
    files = [str(mock_project / "src" / "main.py")]
    project_client.post("/api/project/settings", json={
        "project_path": proj_path,
        "settings": {"staging_list": files}
    })
    
    res = project_client.get(f"/api/project/config?path={proj_path}")
    staged = res.json()["staging_list"]
    assert len(staged) == 1
    assert "main.py" in staged[0]

def test_settings_whitelist_blocks_protected_keys(project_client, mock_project):
    """Verify that update_project_settings blocks writes to protected keys."""
    proj_path = str(mock_project)
    original_groups = project_client.get(f"/api/project/config?path={proj_path}").json()["groups"]
    project_client.post("/api/project/settings", json={
        "project_path": proj_path,
        "settings": {"groups": {}, "notes": {"evil": "injected"}}
    })
    config = project_client.get(f"/api/project/config?path={proj_path}").json()
    assert config["groups"] == original_groups
    assert "evil" not in config["notes"]

def test_settings_whitelist_allows_safe_keys(project_client, mock_project):
    """Verify that whitelisted keys CAN be updated."""
    proj_path = str(mock_project)
    project_client.post("/api/project/settings", json={
        "project_path": proj_path,
        "settings": {"excludes": "*.bak", "max_search_size_mb": 10}
    })
    config = project_client.get(f"/api/project/config?path={proj_path}").json()
    assert config["excludes"] == "*.bak"
    assert config["max_search_size_mb"] == 10

def test_api_move_cross_project_blocked(project_client, mock_project):
    """Verify cross-project move is rejected."""
    import tempfile
    other_dir = tempfile.mkdtemp(prefix="fctx_other_")
    try:
        project_client.post("/api/open", json={"path": other_dir})
        src = str(mock_project / "src" / "main.py")
        res = project_client.post("/api/fs/move", json={
            "src_paths": [src], "dst_dir": other_dir
        })
        # My hardening now returns 403 for cross-project move
        assert res.status_code == 403
        assert "cross-project" in res.json()["detail"]
    finally:
        import shutil
        shutil.rmtree(other_dir, ignore_errors=True)

def test_api_move_returns_skipped_info(project_client, mock_project, system_dir):
    """Verify move to unsafe path returns skipped paths."""
    src = str(mock_project / "src" / "main.py")
    res = project_client.post("/api/fs/move", json={
        "src_paths": [src], "dst_dir": system_dir
    })
    data = res.json()
    assert res.status_code in (200, 403)
    if res.status_code == 200:
        assert src in data.get("skipped", [])

def test_stream_tool_win_safe_execution(mock_project):
    """Verify stream_tool platform bridge."""
    import sys
    test_file = mock_project / "src" / "main.py"
    template = f'"{sys.executable}" -c "print(\'STREAM_OK\')"'
    results = list(ActionBridge.stream_tool(template, str(test_file), mock_project))
    outputs = [r for r in results if "out" in r]
    assert len(outputs) > 0
    assert "STREAM_OK" in outputs[0]["out"]

def test_api_recent_projects_key_unification(project_client, mock_project):
    """Verify that recent projects use last_directory key."""
    from file_cortex_core import PathValidator
    project_client.post("/api/open", json={"path": str(mock_project)})
    res = project_client.get("/api/recent_projects")
    projects = res.json()
    norm_target = PathValidator.norm_path(mock_project)
    assert any(PathValidator.norm_path(p["path"]) == norm_target for p in projects)

def test_get_node_info_no_resource_warning(project_client, mock_project):
    """Verify no ResourceWarning from os.scandir handle leak."""
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        res = project_client.post("/api/fs/children", json={"path": str(mock_project)})
        assert res.status_code == 200
        resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
        assert len(resource_warnings) == 0

def test_api_update_tools_and_categories(project_client, mock_project):
    """Verify dedicated endpoints for tools and categories."""
    proj_path = str(mock_project)
    
    # Update tools
    tools = {"Ping": "ping {name}"}
    res_t = project_client.post("/api/project/tools", json={"project_path": proj_path, "tools": tools})
    assert res_t.status_code == 200
    
    # Update categories
    cats = {"Backups": "backups"}
    res_c = project_client.post("/api/project/categories", json={"project_path": proj_path, "categories": cats})
    assert res_c.status_code == 200
    
    # Verify via config
    config = project_client.get(f"/api/project/config?path={proj_path}").json()
    assert config["custom_tools"]["Ping"] == "ping {name}"
    assert config["quick_categories"]["Backups"] == "backups"

def test_api_update_categories_blocks_traversal(project_client, mock_project):
    """Verify validation in categories update."""
    proj_path = str(mock_project)
    res = project_client.post("/api/project/categories", json={
        "project_path": proj_path, 
        "categories": {"Evil": "../../../etc"}
    })
    assert res.status_code == 400
    assert ".." in res.json()["detail"]
