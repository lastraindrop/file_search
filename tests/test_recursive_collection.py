import pytest
import pathlib
import os
import shutil
from file_cortex_core import FileUtils, ContextFormatter

def test_flatten_paths_recursion_and_dedup(tmp_path):
    """
    Test that flatten_paths correctly expands directories and removes duplicates.
    """
    root = tmp_path / "project"
    root.mkdir()
    
    sub = root / "sub"
    sub.mkdir()
    
    f1 = root / "file1.txt"
    f1.write_text("content1")
    
    f2 = sub / "file2.txt"
    f2.write_text("content2")
    
    # Test Input: [root, f1, f2]
    # f1 and f2 are inside root, so adding all three should only yield f1 and f2.
    paths = [str(root), str(f1), str(f2)]
    
    flattened = FileUtils.flatten_paths(paths, root_dir=str(root), use_gitignore=False)
    
    # Should only have 2 unique files
    assert len(flattened) == 2
    assert any(str(f1.resolve()) in f for f in flattened)
    assert any(str(f2.resolve()) in f for f in flattened)

def test_flatten_paths_with_ignore(tmp_path):
    """
    Test that flatten_paths respects exclusion patterns during expansion.
    """
    root = tmp_path / "project"
    root.mkdir()
    
    f_ok = root / "keep.txt"
    f_ok.write_text("ok")
    
    f_ignore = root / "ignore_me.log"
    f_ignore.write_text("ignore")
    
    # Test with manual exclude
    paths = [str(root)]
    flattened = FileUtils.flatten_paths(paths, root_dir=str(root), 
                                       manual_excludes=["*.log"], 
                                       use_gitignore=False)
    
    assert len(flattened) == 1
    assert str(f_ok.resolve()) in flattened[0]
    assert not any(".log" in f for f in flattened)

def test_context_formatter_recursive(tmp_path):
    """
    Test that ContextFormatter.to_markdown recursive expansion works.
    """
    root = tmp_path / "project"
    root.mkdir()
    f1 = root / "f1.txt"; f1.write_text("data1")
    
    # Pass directory to to_markdown
    result = ContextFormatter.to_markdown([str(root)], root_dir=str(root), use_gitignore=False)
    
    assert "File: f1.txt" in result
    assert "data1" in result
