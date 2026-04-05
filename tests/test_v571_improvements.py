import pytest
import os
import pathlib
import threading
import shutil
from file_cortex_core import DataManager, PathValidator, ContextFormatter, NoiseReducer
from file_cortex_core.search import SHARED_SEARCH_POOL
from web_app import app
from fastapi.testclient import TestClient

def test_v571_datamanager_lock_protection():
    """Verify that update_project_settings uses a lock and filters keys correctly."""
    dm = DataManager()
    p = "e:/test_proj"
    dm.data["projects"][p] = {"staging_list": [], "custom_tools": {}, "max_search_size_mb": 50}
    
    # Use a key that IS in MUTABLE_SETTINGS
    def worker():
        for i in range(10):
            dm.update_project_settings(p, {"max_search_size_mb": i})
            
    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    # Check that it survived and has a valid value
    final_val = dm.get_project_data(p)["max_search_size_mb"]
    assert 0 <= final_val <= 9

def test_v571_webapp_execute_tool_keyerror_fix():
    """Verify api_execute_tool doesn't KeyError if custom_tools is missing."""
    client = TestClient(app)
    dm = DataManager()
    p = "e:/test_proj_unsafe"
    dm.data["projects"][p] = {} 
    
    response = client.post("/api/execute_tool", json={
        "project_path": p,
        "tool_name": "non_existent",
        "file_path": "e:/test.txt"
    })
    # Previously would have been 500 (KeyError), now 404 (Not Found)
    assert response.status_code == 404

def test_v571_security_blacklist(tmp_path):
    """Verify sensitive directories are blocked during project registration."""
    for sensitive in [".git", ".env", "node_modules", "__pycache__"]:
        p = tmp_path / sensitive
        p.mkdir(parents=True, exist_ok=True)
        with pytest.raises(PermissionError, match="Cannot register sensitive directory"):
            PathValidator.validate_project(str(p))

def test_v571_oom_protection(tmp_path):
    """Verify ContextFormatter respects max_bytes."""
    large_file = tmp_path / "large_file.txt"
    with open(large_file, "w") as f:
        f.write("A" * 1024 * 1024 * 2) # 2MB
    
    md = ContextFormatter.to_markdown([str(large_file)], root_dir=str(tmp_path))
    assert "skipped by NoiseReducer" in md or len(md) < 2 * 1024 * 1024

def test_v571_noise_reducer_base64():
    """Verify Base64 chunk detection."""
    base64_logic = "AGFzZGZhc2RmYXNkZmFzZGY" * 20 # > 400 chars
    content = f"Normal text\n{base64_logic}\nEnd text"
    cleaned = NoiseReducer.clean(content)
    assert "Normal text" in cleaned
    assert "End text" in cleaned
    assert "Base64-like block" in cleaned
    assert base64_logic not in cleaned

def test_v571_search_pool_atexit():
    """Verify SHARED_SEARCH_POOL is defined."""
    assert SHARED_SEARCH_POOL is not None
