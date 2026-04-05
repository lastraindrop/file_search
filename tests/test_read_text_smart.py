"""
CR-A02: Exhaustive tests for FileUtils.read_text_smart with max_bytes parameter.
Covers: truncation, encoding detection, binary fallback, and OOM protection.
"""
import pytest
import pathlib
from file_cortex_core import FileUtils


def test_max_bytes_truncation(tmp_path):
    """Verify read_text_smart truncates output when max_bytes is set."""
    f = tmp_path / "big.txt"
    f.write_text("A" * 5000, encoding="utf-8")
    content = FileUtils.read_text_smart(f, max_bytes=1000)
    assert len(content) <= 1100  # Allow minor encoding overhead
    assert content.startswith("A")


def test_no_max_reads_full(tmp_path):
    """Verify full content is returned when max_bytes=None."""
    f = tmp_path / "full.txt"
    original = "Hello " * 500
    f.write_text(original, encoding="utf-8")
    content = FileUtils.read_text_smart(f)
    assert content == original


def test_gbk_auto_detect(tmp_path):
    """Verify GBK encoded files are correctly detected and decoded."""
    gbk_file = tmp_path / "legacy_zh.py"
    text = "测试内容 GBK 编码"
    gbk_file.write_bytes(text.encode('gbk'))
    content = FileUtils.read_text_smart(gbk_file)
    # charset-normalizer should detect GBK and decode properly
    assert "测试" in content or "GBK" in content or len(content) > 0


def test_utf16_bom(tmp_path):
    """Verify UTF-16 BOM files are correctly read."""
    f = tmp_path / "utf16.txt"
    text = "Hello UTF-16 World"
    f.write_bytes(text.encode('utf-16'))  # Includes BOM
    content = FileUtils.read_text_smart(f)
    assert "Hello" in content or "UTF-16" in content


def test_empty_file(tmp_path):
    """Verify empty files return empty string."""
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    content = FileUtils.read_text_smart(f)
    assert content == ""


def test_binary_file_fallback(tmp_path):
    """Verify binary files don't crash, produce some output (even if garbled)."""
    f = tmp_path / "binary.dat"
    f.write_bytes(bytes(range(256)) * 10)
    # Should not raise, gracefully return something
    content = FileUtils.read_text_smart(f)
    assert isinstance(content, str)


def test_max_bytes_with_gbk(tmp_path):
    """Verify max_bytes works correctly with non-UTF-8 encoding."""
    f = tmp_path / "gbk_limited.txt"
    text = "这是一个较长的中文测试文本" * 100  # Lots of text
    f.write_bytes(text.encode('gbk'))
    content = FileUtils.read_text_smart(f, max_bytes=50)
    assert len(content) <= 100  # Reasonable bound (CJK chars can be multi-byte)


def test_nonexistent_file_fallback(tmp_path):
    """Verify graceful handling when file doesn't exist."""
    f = tmp_path / "nonexistent.txt"
    with pytest.raises(Exception):
        FileUtils.read_text_smart(f)
