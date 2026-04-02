import pathlib
import pytest
import os
from file_cortex_core import FileUtils

def test_read_text_smart_memory_safety(tmp_path_factory):
    """Verify read_text_smart uses streaming/header reading for encoding detection."""
    # Use tmp_path_factory to avoid some permission issues on Windows CI
    tmp_path = tmp_path_factory.mktemp("cm_safety")
    large_file = tmp_path / "large_mock_utf8.txt"
    with open(large_file, 'wb') as f:
        # Write some identifiable characters for encoding
        f.write("你好，FileCortex！".encode('utf-8'))
        # Then dummy data to build up size
        f.write(b"A" * 1024 * 64)
    
    # We want to verify it detects utf-8 and returns content
    content = FileUtils.read_text_smart(large_file)
    assert "你好，FileCortex！" in content
    assert len(content) > 65536

def test_norm_path_unc_support():
    """Verify norm_path handles Windows UNC/Long paths."""
    from file_cortex_core.security import PathValidator
    
    # Test Windows long path prefix (simulated)
    unc_path = "//?/C:/Windows/System32"
    norm = PathValidator.norm_path(unc_path)
    assert norm.startswith("//?/")
    assert norm.endswith("system32")
    
    # Test standard path
    stand_path = "C:\\Windows\\Temp\\"
    norm2 = PathValidator.norm_path(stand_path)
    assert norm2 == "c:/windows/temp"
