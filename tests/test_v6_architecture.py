import pytest
import sys
import os
import pathlib
import subprocess
from file_cortex_core import DataManager, PathValidator, FileUtils

def test_package_imports():
    """Verify that all core components can be imported from the package structure."""
    try:
        from file_cortex_core.config import DataManager as DM
        from file_cortex_core.security import PathValidator as PV
        from file_cortex_core.utils import FileUtils as FU
        from file_cortex_core.actions import FileOps, ActionBridge
        from file_cortex_core.search import search_generator
    except ImportError as e:
        pytest.fail(f"Package import failed: {e}")

def test_singleton_isolation_across_modules(clean_config):
    """Verify that DataManager singleton is shared correctly across different module imports."""
    from file_cortex_core.config import DataManager as DM1
    from file_cortex_core.actions import DataManager as DM2
    
    assert DM1() is DM2()
    assert DM1() is DataManager()

def test_entry_point_argparse_logic():
    """Verify that the web_app main() function handles basic CLI flags (dry run)."""
    from web_app import main
    import sys
    from unittest.mock import patch
    
    # Mock sys.argv to simulate 'fctx-web --help' or similar
    # We use --help as it typically exits, but we can mock uvicorn.run to prevent actual server start
    with patch('sys.argv', ['fctx-web', '--port', '8888', '--host', '127.0.0.1']):
        with patch('uvicorn.run') as mock_run:
            main()
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert kwargs['port'] == 8888
            assert kwargs['host'] == '127.0.0.1'

def test_path_validator_norm_path_consistency():
    """Verify that norm_path is deterministic across different input types."""
    raw = "C:\\Users\\Test/Documents" if os.name == 'nt' else "/home/user/../user/docs"
    p_str = PathValidator.norm_path(raw)
    p_path = PathValidator.norm_path(pathlib.Path(raw))
    
    assert p_str == p_path
    assert "\\" not in p_str
    if os.name == 'nt':
        assert p_str == p_str.lower()

def test_file_utils_read_text_smart_oom_protection(tmp_path):
    """Verify that read_text_smart respects max_bytes to prevent OOM."""
    large_file = tmp_path / "large.txt"
    large_file.write_text("A" * 2000, encoding="utf-8")
    
    content = FileUtils.read_text_smart(large_file, max_bytes=100)
    assert len(content.encode('utf-8')) <= 200 # Allow some buffer for encoding/msg
    assert "TRUNCATED" in content or len(content) < 2000
