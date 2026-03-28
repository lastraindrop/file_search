import pytest
import pathlib
import tempfile
import shutil
import os
from fastapi.testclient import TestClient
from web_app import app
from file_cortex_core import DataManager

@pytest.fixture
def mock_project():
    """Creates a temporary project directory with various files."""
    temp_dir = tempfile.mkdtemp(prefix="fctx_mock_")
    base = pathlib.Path(temp_dir)
    
    # Standard files
    (base / "src").mkdir()
    (base / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (base / "src" / "utils.js").write_text("console.log('test'); print('done')", encoding="utf-8")
    
    # New files for permutations
    (base / "config.json").write_text("{}", encoding="utf-8")
    (base / "data.bin").write_bytes(b"\x00\xff\x00\xffhello")
    
    # Binary file
    (base / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    
    # Empty file (edge case)
    (base / "empty.txt").write_text("", encoding="utf-8")
    
    # Gitignore and ignored files
    (base / ".gitignore").write_text("*.log\nnode_modules/", encoding="utf-8")
    (base / "error.log").write_text("some error", encoding="utf-8")
    (base / "node_modules").mkdir()
    (base / "node_modules" / "package.json").write_text("{}", encoding="utf-8")
    
    yield base
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def stress_project():
    """Creates a temporary project with multiple directories and 100+ files."""
    temp_dir = tempfile.mkdtemp(prefix="fctx_stress_")
    base = pathlib.Path(temp_dir)
    
    for i in range(10):
        d = base / f"dir_{i}"
        d.mkdir()
        for j in range(10):
            f = d / f"file_{j}.txt"
            f.write_text(f"Content in file {i}-{j} with keyword_target_{j}", encoding="utf-8")
            
    yield base
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def clean_config():
    """Provides a fresh DataManager with a temporary config file."""
    temp_dir = tempfile.mkdtemp()
    config_path = pathlib.Path(temp_dir) / "test_config.json"
    
    from unittest.mock import patch
    from file_cortex_core import FileUtils
    with patch('file_cortex_core.config.CONFIG_FILE', config_path):
        # Full Reset for implementation consistency
        DataManager._instance = None
        FileUtils.clear_cache()
        dm = DataManager()
        dm.config_path = config_path
        yield dm
        # Cleanup
        DataManager._instance = None
        FileUtils.clear_cache()
        
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def api_client():
    """FastAPI TestClient instance."""
    return TestClient(app)

@pytest.fixture
def project_client(api_client, mock_project):
    """Client with a project already 'opened' and registered."""
    api_client.post("/api/open", json={"path": str(mock_project)})
    return api_client

@pytest.fixture
def system_dir():
    """Returns a platform-specific blocked system directory."""
    if os.name == 'nt':
        return "C:/Windows"
    return "/etc"
