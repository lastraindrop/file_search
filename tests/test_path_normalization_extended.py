"""
CR-A05: Extended path normalization tests covering UNC, empty,
symlinks, case sensitivity, and trailing slashes.
"""
import pytest
import os
import pathlib
from file_cortex_core import PathValidator


def test_trailing_slash_consistency():
    """Verify trailing slash is normalized away."""
    a = PathValidator.norm_path("/some/path/")
    b = PathValidator.norm_path("/some/path")
    assert a == b


@pytest.mark.skipif(os.name != 'nt', reason="Windows-only")
def test_drive_case_insensitive():
    """Verify Windows drive letters are case-insensitive."""
    a = PathValidator.norm_path("C:/Users/test")
    b = PathValidator.norm_path("c:/Users/test")
    assert a == b


@pytest.mark.skipif(os.name != 'nt', reason="Windows-only")
def test_unc_path_normalization():
    """Verify UNC paths are handled without crashing."""
    result = PathValidator.norm_path(r"\\server\share\dir")
    assert "server" in result
    assert "share" in result


def test_dotdot_normalization():
    """Verify double-dot paths are resolved."""
    result = PathValidator.norm_path("/some/path/../other")
    assert ".." not in result


def test_chinese_characters_in_path(tmp_path):
    """Verify Chinese characters in paths are preserved."""
    chinese_dir = tmp_path / "中文目录"
    chinese_dir.mkdir()
    result = PathValidator.norm_path(str(chinese_dir))
    assert "中文目录" in result


def test_pathlib_input(tmp_path):
    """Verify pathlib.Path objects are accepted."""
    result = PathValidator.norm_path(tmp_path / "subdir")
    assert isinstance(result, str)
    assert "subdir" in result


def test_is_safe_with_symlink(tmp_path):
    """Verify is_safe handles symlinks correctly."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "file.txt").write_text("test")
    
    link_dir = tmp_path / "link"
    try:
        link_dir.symlink_to(real_dir)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported")
    
    root = str(tmp_path)
    # Link within project should be safe
    assert PathValidator.is_safe(str(link_dir / "file.txt"), root) is True


def test_is_safe_empty_root(tmp_path):
    """Verify is_safe handles edge case of empty root."""
    assert PathValidator.is_safe(str(tmp_path / "file.txt"), "") is False
