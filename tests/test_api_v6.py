import pytest
import os
import pathlib
import json
from file_cortex_core import PathValidator, FormatUtils

# -----------------------------------------------------------------------------
# 1. Project & Browser Core APIs
# -----------------------------------------------------------------------------

def test_api_browser_contracts(project_client, mock_project):
    """Integrated Test: Open -> Children -> Content -> Recent."""
    # 1. Open
    res_open = project_client.post("/api/open", json={"path": str(mock_project)})
    assert res_open.status_code == 200
    root_data = res_open.json()
    assert root_data["path"] == PathValidator.norm_path(mock_project)
    
    # 2. Children
    res_children = project_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res_children.status_code == 200
    children = res_children.json()["children"]
    assert any(c["name"] == "src" for c in children)
    # Verify UI Contract (Contract Audit merged)
    child = children[0]
    for key in ["name", "path", "type", "size_fmt", "mtime_fmt", "has_children"]:
        assert key in child

    # 3. Content
    main_py = str(mock_project / "src" / "main.py")
    res_content = project_client.get(f"/api/content?path={main_py}")
    assert res_content.status_code == 200
    data = res_content.json()
    assert "content" in data
    assert "encoding" in data
    assert "is_truncated" in data
    
    # 4. Recent
    res_recent = project_client.get("/api/recent_projects")
    assert any(PathValidator.norm_path(p["path"]) == PathValidator.norm_path(mock_project) for p in res_recent.json())

@pytest.mark.parametrize("file_type,expected_content", [
    ("binary", "--- Binary File (Preview Unavailable) ---"),
    ("large", None) # Handled by truncation test
])
def test_api_content_edge_cases(project_client, mock_project, file_type, expected_content):
    """Combined check for binary detection and truncation."""
    if file_type == "binary":
        target = str(mock_project / "data.bin")
        res = project_client.get(f"/api/content?path={target}")
        assert expected_content in res.json()["content"]
    elif file_type == "large":
        large_f = mock_project / "large_trunc.txt"
        large_f.write_text("X" * 1500000) # 1.5MB
        res = project_client.get(f"/api/content?path={str(large_f)}")
        # Check truncation (MAX_PREVIEW is 1,000,000 for 1MB)
        assert len(res.json()["content"]) <= 1000100 
        assert res.json()["is_truncated"] is True

# -----------------------------------------------------------------------------
# 2. Configuration & Settings Management
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("request_format", ["flat", "nested"])
def test_api_global_settings_sync(project_client, request_format):
    """Consolidated Test: Global settings update (Forward & backward compatible)."""
    endpoint = "/api/config/global"
    payload = {"preview_limit_mb": 2.5, "token_threshold": 300000}
    if request_format == "nested":
        payload = {"settings": payload}
    
    res = project_client.post(endpoint, json=payload)
    assert res.status_code == 200
    
    # Verify via both GET endpoints
    for route in ["/api/config/global", "/api/global/settings"]:
        data = project_client.get(route).json()
        assert data["preview_limit_mb"] == 2.5
        assert data["token_threshold"] == 300000

def test_api_project_specific_metadata(project_client, mock_project):
    """Test tools, Categories, and Favorites update endpoints."""
    path = str(mock_project)
    
    # Tools
    project_client.post("/api/project/tools", json={"project_path": path, "tools": {"Harden": "fctx polish"}})
    # Categories
    project_client.post("/api/project/categories", json={"project_path": path, "categories": {"Legacy": "old_src"}})
    # Settings (Whitelisting check)
    project_client.post("/api/project/settings", json={"project_path": path, "settings": {"excludes": "*.log", "illegal": "leak"}})
    
    config = project_client.get(f"/api/project/config?path={path}").json()
    assert config["custom_tools"]["Harden"] == "fctx polish"
    assert config["quick_categories"]["Legacy"] == "old_src"
    assert config["excludes"] == "*.log"
    assert "illegal" not in config # Whitelisted keys only

# -----------------------------------------------------------------------------
# 3. File Operations & Security
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("op", ["move", "rename", "delete"])
def test_api_fs_ops_safety(project_client, mock_project, system_dir, op):
    """stress test security of file operations via API."""
    src = str(mock_project / "src" / "main.py")
    
    if op == "move":
        # Cross-project or system-dir move should be rejected/skipped
        res = project_client.post("/api/fs/move", json={"src_paths": [src], "dst_dir": system_dir})
        assert res.status_code in (403, 200) # 403 for strict, 200 {skipped} for partial
        if res.status_code == 200: assert src in res.json().get("skipped", [])
    elif op == "rename":
        res = project_client.post("/api/fs/rename", json={"project_path": str(mock_project), "path": src, "new_name": "../../etc/passwd"})
        assert res.status_code != 200 # Should trigger PathValidator
    elif op == "delete":
        res = project_client.post("/api/fs/delete", json={"project_path": str(mock_project), "paths": ["../../../etc/passwd"]})
        assert res.status_code != 200

# -----------------------------------------------------------------------------
# 4. Collection, Stats & Generation
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["markdown", "xml"])
def test_api_full_generation_flow(project_client, mock_project, fmt):
    """E2E flow: Open -> Stage -> Stats -> Generate."""
    root = str(mock_project)
    f1 = str(mock_project / "src" / "main.py")
    
    # 1. Stage
    project_client.post("/api/project/settings", json={"project_path": root, "settings": {"staging_list": [f1]}})
    
    # 2. Stats
    res_stats = project_client.post("/api/project/stats", json={"paths": [f1], "project_path": root})
    assert res_stats.json()["total_tokens"] > 0
    
    # 3. Generate
    res_gen = project_client.post("/api/generate", json={"files": [f1], "project_path": root, "export_format": fmt})
    assert res_gen.status_code == 200
    content = res_gen.json()["content"]
    if fmt == "xml":
        assert "<context>" in content
    else:
        assert "```python" in content

# -----------------------------------------------------------------------------
# 5. Advanced Resilience
# -----------------------------------------------------------------------------

def test_api_search_websocket_protocol(project_client, mock_project):
    """Verify WebSocket search flow and stop events."""
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        results = []
        while True:
            data = ws.receive_json()
            if data.get("status") == "DONE": break
            if data.get("status") == "ERROR": pytest.fail(f"Search WS error: {data}")
            results.append(data)
        assert len(results) >= 1
