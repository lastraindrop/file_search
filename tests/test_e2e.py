import pytest
from fastapi.testclient import TestClient
from web_app import app
import json
import time

client = TestClient(app)

def test_full_workflow_e2e(mock_project):
    """Simulates: Open -> Browse -> Search -> Stage -> Generate"""
    
    # 1. Open Project
    res = client.post("/api/open", json={"path": str(mock_project)})
    assert res.status_code == 200
    
    # 2. Browse Children of root
    res = client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    children = res.json()["children"]
    src_node = next(c for c in children if c["name"] == "src")
    
    # 3. Browse Children of 'src'
    res = client.post("/api/fs/children", json={"path": src_node["path"]})
    assert res.status_code == 200
    src_children = res.json()["children"]
    assert any(c["name"] == "main.py" for c in src_children)
    
    # 4. Search (Simulate WebSocket behavior via core search logic for simplicity, or use TestClient's websocket)
    # The websocket_search in web_app uses a generator. 
    # For a real E2E, we'd use client.websocket_connect, but let's test the logic path.
    with client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&mode=smart") as websocket:
        data = websocket.receive_json()
        assert "main.py" in data["name"]
        data_done = websocket.receive_json()
        assert data_done["status"] == "DONE"
        
    # 5. Generate Context for selected files
    files = [str(mock_project / "src" / "main.py")]
    res = client.post("/api/generate", json={"files": files})
    assert res.status_code == 200
    assert "File: main.py" in res.json()["content"]
    
    print("\n✓ E2E Workflow Completed Successfully")
