import pytest
from fastapi.testclient import TestClient
from web_app import app
import os

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def registered_client(client, mock_project):
    client.post("/api/open", json={"path": str(mock_project)})
    return client

def test_full_workflow_e2e(registered_client, mock_project):
    """Simulates: Open -> Browse -> Search -> Stage -> Generate"""
    # Browse
    res = registered_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    
    # WebSocket Search
    with registered_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        assert "size" in data
        
    # Generate
    files = [str(mock_project / "src" / "main.py")]
    res = registered_client.post("/api/generate", json={"files": files})
    assert res.status_code == 200
    assert "File: main.py" in res.json()["content"]

def test_file_lifecycle_e2e(registered_client, mock_project):
    """Lifecycle: Search Old -> Create New -> Rename -> Delete -> Search None"""
    # 1. Search for a file that DOES exist
    with registered_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        
    # 2. Rename 'main.py' to 'core_main.py'
    old_path = mock_project / "src" / "main.py"
    new_name = "core_main.py"
    res = registered_client.post("/api/fs/rename", json={
        "project_path": str(mock_project),
        "path": str(old_path),
        "new_name": new_name
    })
    assert res.status_code == 200
    new_path = res.json()["new_path"]
    assert "core_main.py" in new_path
    
    # 3. Search for 'core_main.py'
    with registered_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=core_main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert "core_main.py" in data["name"]
        
    # 4. Delete the renamed file
    res = registered_client.post("/api/fs/delete", json={
        "project_path": str(mock_project),
        "paths": [new_path]
    })
    assert res.status_code == 200
    
    # 5. Search for it again - should be 0 results
    with registered_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=core_main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert data["status"] == "DONE" # No results found before DONE

def test_settings_and_search_workflow_e2e(registered_client, mock_project):
    """Tests: Open -> Update Excludes -> Search -> Verify exclusion is respected."""
    # 1. Search initially (should find main.py)
    with registered_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        ws.receive_json() # DONE

    # 2. Update settings to exclude .py files
    registered_client.post("/api/project/settings", json={
        "project_path": str(mock_project),
        "settings": {"excludes": "*.py"}
    })
    
    # 3. Search again (should NOT find main.py)
    with registered_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert data["status"] == "DONE" # No results found
