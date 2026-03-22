import pytest
from fastapi.testclient import TestClient
from web_app import app
import os
import pathlib
import time

client = TestClient(app)

def test_full_workflow_e2e(mock_project):
    """Simulates: Open -> Browse -> Search -> Stage -> Generate"""
    client.post("/api/open", json={"path": str(mock_project)})
    
    # Browse
    res = client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    
    # WebSocket Search
    with client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        assert "size" in data
        
    # Generate
    files = [str(mock_project / "src" / "main.py")]
    res = client.post("/api/generate", json={"files": files})
    assert res.status_code == 200
    assert "File: main.py" in res.json()["content"]

def test_file_lifecycle_e2e(mock_project):
    """Lifecycle: Search Old -> Create New -> Rename -> Delete -> Search None"""
    client.post("/api/open", json={"path": str(mock_project)})
    
    # 1. Search for a file that DOES exist
    with client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert "main.py" in data["name"]
        
    # 2. Rename 'main.py' to 'core_main.py'
    old_path = mock_project / "src" / "main.py"
    new_name = "core_main.py"
    res = client.post("/api/fs/rename", json={"path": str(old_path), "new_name": new_name})
    assert res.status_code == 200
    new_path = res.json()["new_path"]
    assert "core_main.py" in new_path
    
    # 3. Search for 'core_main.py'
    with client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=core_main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert "core_main.py" in data["name"]
        
    # 4. Delete the renamed file
    res = client.post("/api/fs/delete", json={"paths": [new_path]})
    assert res.status_code == 200
    
    # 5. Search for it again - should be 0 results
    with client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=core_main.py&mode=exact") as ws:
        data = ws.receive_json()
        assert data["status"] == "DONE" # No results found before DONE
