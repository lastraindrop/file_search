import pytest
from fastapi.testclient import TestClient
from web_app import app
import os

# E2E tests using fixtures from conftest.py

def test_full_workflow_e2e(project_client, mock_project):
    """Simulates: Open -> Browse -> Search -> Stage -> Generate"""
    # Browse
    res = project_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    
    # WebSocket Search
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        assert "size" in data
        
    # Generate
    files = [str(mock_project / "src" / "main.py")]
    res = project_client.post("/api/generate", json={"files": files})
    assert res.status_code == 200
    assert "File: main.py" in res.json()["content"]

def test_file_lifecycle_e2e(project_client, mock_project):
    """Lifecycle: Search Old -> Create New -> Rename -> Delete -> Search None"""
    # 1. Search for a file that DOES exist
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        
    # 2. Rename 'main.py' to 'core_main.py'
    old_path = mock_project / "src" / "main.py"
    new_name = "core_main.py"
    res = project_client.post("/api/fs/rename", json={
        "project_path": str(mock_project),
        "path": str(old_path),
        "new_name": new_name
    })
    assert res.status_code == 200
    new_path = res.json()["new_path"]
    assert "core_main.py" in new_path
    
    # 3. Search for 'core_main.py'
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=core_main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert "core_main.py" in data["name"]
        
    # 4. Delete the renamed file
    res = project_client.post("/api/fs/delete", json={
        "project_path": str(mock_project),
        "paths": [new_path]
    })
    assert res.status_code == 200
    
    # 5. Search for it again - should be 0 results
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=core_main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert data["status"] == "DONE" # No results found before DONE

def test_settings_and_search_workflow_e2e(project_client, mock_project):
    """Tests: Open -> Update Excludes -> Search -> Verify exclusion is respected."""
    # 1. Search initially (should find main.py)
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        ws.receive_json() # DONE

    # 2. Update settings to exclude .py files
    project_client.post("/api/project/settings", json={
        "project_path": str(mock_project),
        "settings": {"excludes": "*.py"}
    })
    
    # 3. Search again (should NOT find main.py)
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert data["status"] == "DONE" # No results found

# --- V5.0 Orchestration E2E ---

def test_v5_workspace_orchestration_e2e(project_client, mock_project):
    """Simulates: Search -> Discover -> Configure Tool/Cat -> Categorize -> Execute"""
    import sys
    
    # 1. Search to find target
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=utils.js&mode=smart") as ws:
        data = ws.receive_json()
        target_file = data["path"]
        assert "utils.js" in target_file
        ws.receive_json() # DONE

    # 2. Configure project for orchestration
    cmd = f'"{sys.executable}" -c "print(\'E2E_OK_for_{{name}}\')"'
    project_client.post("/api/project/settings", json={
        "project_path": str(mock_project),
        "settings": {
            "quick_categories": {"JS_Bin": "scripts/js"},
            "custom_tools": {"Tester": cmd}
        }
    })

    # 3. Categorize (Move) the discovered file
    res = project_client.post("/api/actions/categorize", json={
        "project_path": str(mock_project),
        "paths": [target_file],
        "category_name": "JS_Bin"
    })
    assert res.status_code == 200
    moved_path = res.json()["paths"][0]
    assert "scripts" in moved_path and "js" in moved_path
    
    # 4. Execute tool on the newly moved file
    res = project_client.post("/api/actions/execute", json={
        "project_path": str(mock_project),
        "paths": [moved_path],
        "tool_name": "Tester"
    })
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 1
    assert "E2E_OK_for_utils.js" in results[0]["stdout"]
