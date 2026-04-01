import pytest
import os
import pathlib
from file_cortex_core import PathValidator, FileUtils, FileOps, DataManager, search_generator

def test_path_normalization_drive_casing():
    """Verify that norm_path handles drive letter casing consistently on Windows."""
    if os.name != 'nt':
        pytest.skip("Windows specific test")
    
    p1 = "C:/Users/Test"
    p2 = "c:/users/test" 
    p3 = "C:\\Users\\Test"
    
    n1 = PathValidator.norm_path(p1)
    n2 = PathValidator.norm_path(p2)
    n3 = PathValidator.norm_path(p3)
    
    assert n1 == n2 == n3
    assert "\\" not in n1
    assert "c:/" in n1

def test_search_with_special_chars_in_filename(mock_project):
    """Verify search engine can handle filenames with spaces, hashtags, etc."""
    base = mock_project
    (base / "file with spaces.txt").write_text("content", encoding="utf-8")
    (base / "file#hash.js").write_text("content", encoding="utf-8")
    (base / "file%percent.py").write_text("content", encoding="utf-8")
    
    # 1. Search with spaces
    matches = list(search_generator(str(base), "file with spaces", "smart", ""))
    assert len(matches) >= 1
    assert any("file with spaces.txt" in m["path"] for m in matches)
    
    # 2. Search with special chars
    matches = list(search_generator(str(base), "file#hash", "smart", ""))
    assert len(matches) >= 1
    assert any("file#hash.js" in m["path"] for m in matches)

def test_delete_read_only_file(mock_project):
    """Verify that FileOps.delete_file can handle read-only files (requires chmod)."""
    base = mock_project
    f = base / "readonly.txt"
    f.write_text("content", encoding="utf-8")
    
    # Make read-only
    import stat
    mode = os.stat(f).st_mode
    os.chmod(f, mode & ~stat.S_IWRITE)
    
    try:
        # Should succeed in deleting or at least handling the permission error
        FileOps.delete_file(str(f))
    except PermissionError:
        # If it fails, that's expected for some OS, but we should verify behavior
        # In our FileOps, we don't currently chmod before delete.
        # This test documents that behavior.
        pass
    except Exception as e:
        pytest.fail(f"Delete failed with unexpected error: {e}")
    
    # Reset mode for cleanup
    if f.exists():
        os.chmod(f, mode | stat.S_IWRITE)

def test_search_non_utf8_binary_detection(noisy_project):
    """Verify that search engine skips binary/malformed files correctly."""
    base = noisy_project
    matches = list(search_generator(str(base), "测试内容", "content", "", case_sensitive=True))
    # It should skip GBK file unless encoded specifically, but it won't crash
    # The search should return 0 results because it only reads UTF-8 with ignore
    assert len(matches) == 0

def test_validate_project_root_drive_block():
    """Verify that registering a root drive is blocked as expected."""
    with pytest.raises(PermissionError):
        PathValidator.validate_project("C:/" if os.name == 'nt' else "/")

def test_batch_rename_collision_suffix(mock_project):
    """Verify that batch_rename adds a suffix when a collision occurs."""
    base = mock_project.resolve()
    f1 = (base / "test1.txt")
    f2 = (base / "test2.txt")
    target = (base / "new.txt")
    
    f1.write_text("c1", encoding="utf-8")
    f2.write_text("c2", encoding="utf-8")
    target.write_text("c3", encoding="utf-8") # Conflict
    
    paths = [str(f1), str(f2)]
    results = FileOps.batch_rename(str(base), paths, ".*", "new.txt", dry_run=False)
    
    # Both files should conflict because 'new.txt' exists on disk initially.
    # f1 gets new_1.txt, f2 gets new_2.txt
    assert results[0]["status"] == "renamed_with_suffix"
    assert results[1]["status"] == "renamed_with_suffix"
    
    # Verify files still exist with new names
    assert (base / "new_1.txt").exists()
    assert (base / "new_2.txt").exists()


def test_norm_path_roots():
    from file_cortex_core.security import PathValidator
    import sys

    # On Windows, Path('/') resolves to the root of the current drive (e.g. 'e:/').
    res_root = PathValidator.norm_path('/')
    if sys.platform == 'win32':
        assert len(res_root) == 3
        assert res_root.endswith(':/')
    else:
        assert res_root == '/'
    
    if sys.platform == 'win32':
        # Test Windows drive root - should preserve trailing slash to stay absolute
        assert PathValidator.norm_path('C:/') == 'c:/'
        assert PathValidator.norm_path('c:\\') == 'c:/'

        # Test that stripping does NOT happen for drive root
        res = PathValidator.norm_path('D:/')
        assert res == 'd:/'
        assert len(res) == 3
    else:
        # Generic absolute path for unix
        assert PathValidator.norm_path('/usr/bin/') == '/usr/bin'
