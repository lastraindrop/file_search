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
