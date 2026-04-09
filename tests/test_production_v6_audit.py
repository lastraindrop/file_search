import pytest
import os
import pathlib
import json
from file_cortex_core import DataManager, PathValidator, ContextFormatter, FileUtils

@pytest.mark.parametrize("export_format", ["markdown", "xml"])
@pytest.mark.parametrize("use_gitignore", [True, False])
def test_comprehensive_export_flow_permutations(project_client, mock_project, export_format, use_gitignore):
    """
    Requirement 3: Verify end-to-end flow with all parameter combinations.
    Flow: Open -> Generate Context (MD/XML) -> Verify specific markers.
    """
    # 1. Setup mock files
    src = mock_project / "src"
    src.mkdir(exist_ok=True)
    (src / "test.py").write_text("print('hello')", encoding='utf-8')
    (src / "data.txt").write_text("some data", encoding='utf-8')
    
    files_to_stage = [str(src / "test.py"), str(src / "data.txt")]
    
    # 2. Call Generate API
    req_body = {
        "files": files_to_stage,
        "project_path": str(mock_project),
        "export_format": export_format
    }
    
    res = project_client.post("/api/generate", json=req_body)
    assert res.status_code == 200
    data = res.json()
    
    content = data["content"]
    assert "tokens" in data
    
    # 3. Validation based on format
    if export_format == "xml":
        assert "<context>" in content
        assert "</context>" in content
        assert f'path="src/test.py"' in content or 'path="src\\test.py"' in content
        assert "<![CDATA[" in content
    else:
        assert "File: src/test.py" in content or "File: src\\test.py" in content
        assert "```python" in content

def test_unified_settings_architecture_isolation(clean_config):
    """
    Requirement 1 & 4: Verify Unified Settings isolation and inheritance.
    Ensures Global Settings don't leak into Project Schema unnecessarily, but are accessible via API.
    """
    dm = DataManager()
    
    # 1. Test Default Global Settings
    global_s = dm.data.get("global_settings")
    assert global_s is not None
    assert global_s["preview_limit_mb"] == 1.0
    
    # 2. Update Global Settings
    dm.update_global_settings({"preview_limit_mb": 2.5, "theme": "light"})
    assert dm.data["global_settings"]["preview_limit_mb"] == 2.5
    
    # 3. Verify Project Data remains isolated but inherits schema
    proj_path = "C:/TestProject" if os.name == 'nt' else "/tmp/testproject"
    proj_data = dm.get_project_data(proj_path)
    
    assert "excludes" in proj_data
    # Project data should NOT contain global_settings keys directly
    assert "preview_limit_mb" not in proj_data
    
def test_api_global_settings_contract(project_client):
    """
    Requirement 4: Frontend-oriented API contract audit for Global Settings.
    """
    # GET Check
    res = project_client.get("/api/global/settings")
    assert res.status_code == 200
    data = res.json()
    assert "preview_limit_mb" in data
    assert "theme" in data
    
    # POST Check
    new_settings = {"theme": "custom-blue", "token_ratio": 3.5}
    res = project_client.post("/api/global/settings", json={"settings": new_settings})
    assert res.status_code == 200
    
    # Verification
    res_get = project_client.get("/api/global/settings")
    updated = res_get.json()
    assert updated["theme"] == "custom-blue"
    assert updated["token_ratio"] == 3.5

@pytest.mark.parametrize("search_mode", ["smart", "regex", "content"])
def test_search_stability_and_contract(project_client, mock_project, search_mode):
    """
    Requirement 3: Full process verification of search modes.
    Ensures search returns the 'abs_path' required by the hardened GUI logic.
    """
    # Create target file
    (mock_project / "find_me.py").write_text("secret_key = 123 # find me in content", encoding='utf-8')
    
    # We use the search endpoint via websocket or a helper if available. 
    # Since search is mainly WS, we can test the search_generator directly for core logic.
    from file_cortex_core import search_generator
    import threading
    
    stop_event = threading.Event()
    results = list(search_generator(str(mock_project), "find", search_mode, manual_excludes=".git", stop_event=stop_event))
    
    assert len(results) >= 1
    found = results[0]
    
    # Deep Contract Inspection for UI
    required_keys = {"name", "path", "abs_path", "match_type", "size_fmt"}
    for k in required_keys:
        assert k in found, f"Search result missing UI-critical key: {k}"
    
    # Verify absolute path hardening (A1 fix)
    assert os.path.isabs(found["abs_path"])
    assert found["abs_path"].lower().endswith("find_me.py")

def test_project_blueprint_flow(project_client, mock_project):
    """Verify the newly added Blueprint feature through the core logic."""
    (mock_project / "README.md").write_text("# Project", encoding='utf-8')
    (mock_project / "app").mkdir()
    (mock_project / "app" / "core.py").write_text("pass", encoding='utf-8')
    
    blueprint = ContextFormatter.generate_blueprint(str(mock_project), ".git")
    assert "--- PROJECT BLUEPRINT ---" in blueprint
    assert "README.md" in blueprint
    assert "app" in blueprint
