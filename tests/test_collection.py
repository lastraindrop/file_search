import pytest
import pathlib
from file_cortex_core.utils import FormatUtils

def test_collect_paths_basic():
    paths = [r"C:\project\src\main.py", r"C:\project\README.md"]
    root = r"C:\project"
    
    # Relative with NewLine
    res = FormatUtils.collect_paths(paths, root, mode='relative', separator='\\n')
    assert "src\\main.py\nREADME.md" in res or "src/main.py\nREADME.md" in res

    # Absolute with Space
    res = FormatUtils.collect_paths(paths, root, mode='absolute', separator=' ')
    assert str(pathlib.Path(paths[0]).resolve()) in res
    assert str(pathlib.Path(paths[1]).resolve()) in res

def test_collect_paths_custom_sep():
    paths = ["/a/b", "/a/c"]
    res = FormatUtils.collect_paths(paths, "/a", mode='relative', separator=' @')
    # On windows resolve() might change the path, but let's assume relative works
    assert "@" in res

def test_collect_paths_escapes():
    paths = ["file1", "file2"]
    res = FormatUtils.collect_paths(paths, separator="\\t")
    assert "\t" in res
    
    res = FormatUtils.collect_paths(paths, separator="\\n")
    assert "\n" in res

def test_collect_paths_symbols(mock_project):
    """Verify that file prefixes and directory suffixes are applied correctly."""
    root = mock_project
    src_dir = root / "src"
    main_py = src_dir / "main.py"
    
    paths = [str(src_dir), str(main_py)]
    
    # 1. Test with symbols
    res = FormatUtils.collect_paths(paths, str(root), 
                                   mode='relative', 
                                   separator=' ', 
                                   file_prefix='@', 
                                   dir_suffix='/')
    
    # Relative path of src_dir is "src", with suffix it becomes "src/"
    # Relative path of main_py is "src/main.py", with prefix it becomes "@src/main.py"
    # Note: On Windows it might use backslashes depending on str(p.relative_to(root))
    
    parts = res.split(' ')
    assert any(p.rstrip('/').endswith('src') and p.endswith('/') for p in parts)
    assert any(p.startswith('@') and 'main.py' in p for p in parts)

def test_collect_paths_suffix_idempotency(mock_project):
    """Verify that suffix isn't doubled if already present."""
    root = mock_project
    src_dir = root / "src"
    
    res = FormatUtils.collect_paths([str(src_dir)], str(root), 
                                   dir_suffix='/')
    assert res.endswith('/')
    assert not res.endswith('//')
