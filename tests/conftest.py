import pytest
import pathlib
import tempfile
import shutil
import os

@pytest.fixture
def mock_project():
    """Creates a temporary project directory with various files."""
    temp_dir = tempfile.mkdtemp(prefix="ai_workbench_mock_")
    base = pathlib.Path(temp_dir)
    
    # Standard files
    (base / "src").mkdir()
    (base / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (base / "src" / "utils.js").write_text("console.log('test')", encoding="utf-8")
    
    # Binary file
    (base / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    
    # Gitignore and ignored files
    (base / ".gitignore").write_text("*.log\nnode_modules/", encoding="utf-8")
    (base / "error.log").write_text("some error", encoding="utf-8")
    (base / "node_modules").mkdir()
    (base / "node_modules" / "package.json").write_text("{}", encoding="utf-8")
    
    yield base
    
    shutil.rmtree(temp_dir)

@pytest.fixture
def clean_config():
    """Ensures a clean config directory for tests."""
    from core_logic import get_app_dir
    app_dir = get_app_dir()
    config_file = app_dir / "config.json"
    backup_file = app_dir / "config.json.bak"
    
    # Backup existing config
    if config_file.exists():
        shutil.copy(config_file, backup_file)
        os.remove(config_file)
    
    yield config_file
    
    # Restore backup
    if backup_file.exists():
        shutil.move(backup_file, config_file)
