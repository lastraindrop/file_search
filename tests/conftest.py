import gc
import os
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from file_cortex_core import DataManager
from web_app import app


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure DataManager singleton and global process registry are reset between tests."""
    from file_cortex_core import FileUtils
    from web_app import ACTIVE_PROCESSES

    # Force immediate GC to close unreferenced file handles
    gc.collect()

    with DataManager._lock:
        DataManager._instance = None
    
    yield

    # Cleanup lingering processes to release file locks on Windows
    # Use a more defensive approach
    pids = list(ACTIVE_PROCESSES.keys())
    for pid in pids:
        proc = ACTIVE_PROCESSES.get(pid)
        if proc:
            try:
                if proc.poll() is None:
                    if os.name == 'nt':
                        # Kill the whole tree if possible
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                                     capture_output=True, timeout=5, check=False)
                    else:
                        os.killpg(os.getpgid(pid), 15)
                    proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=1)
                except Exception:
                    pass
            finally:
                ACTIVE_PROCESSES.pop(pid, None)

    # Final sweep
    with DataManager._lock:
        DataManager._instance = None
    
    FileUtils.clear_cache()
    ACTIVE_PROCESSES.clear()

    # CRITICAL: Mandatory GC and sleep for Windows FS synchronization
    gc.collect()
    if os.name == 'nt':
        time.sleep(0.2) # Wait for OS to release file locks


@pytest.fixture
def mock_project(tmp_path):
    """Creates a temporary project directory with various files."""
    base = tmp_path / "mock_project"
    base.mkdir()

    # Standard files
    (base / "src").mkdir()
    (base / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (base / "src" / "utils.js").write_text("console.log('test'); print('done')", encoding="utf-8")

    # New files for permutations
    (base / "config.json").write_text("{}", encoding="utf-8")
    (base / "data.bin").write_bytes(b"\x00\xff\x00\xffhello")
    (base / "README.md").write_text("# Mock Project", encoding="utf-8")

    # Binary file
    (base / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    # Empty file (edge case)
    (base / "empty.txt").write_text("", encoding="utf-8")

    # Gitignore and ignored files
    (base / ".gitignore").write_text("*.log\nnode_modules/", encoding="utf-8")
    (base / "error.log").write_text("some error", encoding="utf-8")
    (base / "node_modules").mkdir()
    (base / "node_modules" / "package.json").write_text("{}", encoding="utf-8")

    return base

@pytest.fixture
def noisy_project(tmp_path):
    """Creates a project with complex encoding, minified code, and noise."""
    base = tmp_path / "noisy_project"
    base.mkdir()

    # 1. GBK Encoded File (Common in some Chinese heritage codebases)
    gbk_file = base / "legacy_zh.py"
    gbk_file.write_bytes(b"\xb2\xe2\xca\xd4\xc4\xda\xc8\xdd")

    # 2. Minified File (Noise)
    min_file = base / "library.min.js"
    long_line = "var a=1;" + "b=2;" * 1000 + "console.log(a+b);"
    min_file.write_text(long_line, encoding="utf-8")

    # 3. Clean File
    clean_file = base / "app.py"
    clean_file.write_text("print('Hello World')", encoding="utf-8")

    return base

@pytest.fixture
def mock_popen(monkeypatch):
    """Mocks subprocess.Popen for safe process management testing."""
    import subprocess
    from unittest.mock import MagicMock

    mock_proc = MagicMock()
    mock_proc.pid = 9999
    mock_proc.stdout = ["Line 1\n", "Line 2\n"]
    mock_proc.stderr = []
    mock_proc.returncode = 0
    mock_proc.poll.return_value = 0
    mock_proc.communicate.return_value = ("stdout", "stderr")

    def _mock_popen_init(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr(subprocess, "Popen", _mock_popen_init)
    return mock_proc

@pytest.fixture
def stress_project(tmp_path):
    """Creates a temporary project with multiple directories and 100+ files."""
    base = tmp_path / "stress_project"
    base.mkdir()

    for i in range(10):
        d = base / f"dir_{i}"
        d.mkdir()
        for j in range(10):
            f = d / f"file_{j}.txt"
            f.write_text(f"Content in file {i}-{j} with keyword_target_{j}", encoding="utf-8")

    return base

@pytest.fixture
def clean_config(tmp_path):
    """Provides a fresh DataManager with a temporary config file."""
    config_path = tmp_path / "test_config.json"

    from unittest.mock import patch

    from file_cortex_core import FileUtils
    with patch('file_cortex_core.config._CONFIG_FILE', config_path):
        # Full Reset for implementation consistency
        DataManager._instance = None
        FileUtils.clear_cache()
        dm = DataManager()
        dm.config_path = config_path
        yield dm
        # Cleanup
        DataManager._instance = None
        FileUtils.clear_cache()

@pytest.fixture
def api_client(tmp_path):
    """FastAPI TestClient instance with isolated config."""
    config_path = tmp_path / "api_test_config.json"

    from unittest.mock import patch

    from file_cortex_core import FileUtils

    with patch('file_cortex_core.config._CONFIG_FILE', config_path):
        DataManager._instance = None
        FileUtils.clear_cache()

        client = TestClient(app)
        yield client

        DataManager._instance = None
        FileUtils.clear_cache()

@pytest.fixture
def project_client(api_client, mock_project):
    """Client with a project already 'opened' and registered."""
    res = api_client.post("/api/open", json={"path": str(mock_project)})
    assert res.status_code == 200
    return api_client

@pytest.fixture
def system_dir():
    """Returns a platform-specific blocked system directory."""
    if os.name == 'nt':
        return os.environ.get("SYSTEMROOT", "C:/Windows")
    return "/etc"
