import pathlib
import pytest
import os
import shutil
from file_cortex_core import FileUtils

def test_read_text_smart_memory_safety(tmp_path):
    """Verify read_text_smart handles large files and multiple encodings safely."""
    test_dir = tmp_path / "encoding_tests"
    test_dir.mkdir(exist_ok=True)
    
    # 1. UTF-8 (Large / Streaming)
    utf8_file = test_dir / "large_utf8.txt"
    with open(utf8_file, 'wb') as f:
        f.write("你好，FileCortex！".encode('utf-8'))
        f.write(b"A" * 1024 * 65) # > 64KB
    
    content = FileUtils.read_text_smart(utf8_file)
    assert "你好" in content
    assert len(content) > 65536
    
    # 2. GBK (Legacy Chinese)
    gbk_file = test_dir / "legacy_gbk.txt"
    with open(gbk_file, 'wb') as f:
        # Repeating the string to provide enough bytes for heuristic success
        f.write(("简体中文GBK内容 - 特色文档流测试 " * 20).encode('gbk'))
    
    content_gbk = FileUtils.read_text_smart(gbk_file)
    assert "简体中文" in content_gbk
    
    # 3. Empty File
    empty_file = test_dir / "empty.txt"
    empty_file.touch()
    assert FileUtils.read_text_smart(empty_file) == ""
    
    # 4. Binary File (Should use fallback)
    bin_file = test_dir / "binary.dat"
    with open(bin_file, 'wb') as f:
        f.write(os.urandom(1024))
    # It shouldn't crash, returns some decoded mess or empty
    FileUtils.read_text_smart(bin_file)

def test_norm_path_unc_support():
    """Verify norm_path handles Windows UNC/Long paths correctly across platforms."""
    from file_cortex_core.security import PathValidator
    import sys
    
    if sys.platform == 'win32':
        # On Windows, abspath preserves the long path prefix //?/
        unc_path = "//?/C:/Windows/System32"
        norm = PathValidator.norm_path(unc_path)
        assert norm.startswith("//?/")
        assert "system32" in norm
    
    # Test standard path (portable behavior)
    stand_path = "tests/test_file.py"
    norm2 = PathValidator.norm_path(stand_path)
    assert "\\" not in norm2
    assert norm2.endswith("tests/test_file.py")
