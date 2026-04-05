"""
CR-C06: Verify that archive_selection correctly calculates relative paths 
within the ZIP file when root_dir is provided as a string.
"""
import pytest
import os
import pathlib
import zipfile
from file_cortex_core import FileOps


def test_archive_with_str_root(mock_project):
    """Verify that root_dir as a string preserves relative path hierarchy."""
    root = str(mock_project)
    f1 = mock_project / "src" / "main.py"
    output_zip = mock_project / "test_hierarchy.zip"
    
    # Pass root as string
    res = FileOps.archive_selection([str(f1)], str(output_zip), root_dir=root)
    
    assert os.path.exists(res)
    with zipfile.ZipFile(res, 'r') as z:
        # Should be "src/main.py" (relative to root), NOT just "main.py"
        names = z.namelist()
        assert any(n.replace("\\", "/") == "src/main.py" for n in names)


def test_archive_nested_dirs(mock_project):
    """Verify recursive directory archiving preserves nested structure."""
    root = str(mock_project)
    src_dir = mock_project / "src"
    output_zip = mock_project / "test_dir.zip"
    
    res = FileOps.archive_selection([str(src_dir)], str(output_zip), root_dir=root)
    
    with zipfile.ZipFile(res, 'r') as z:
        names = [n.replace("\\", "/") for n in z.namelist()]
        # Since src was nested, it should be in the zip
        assert "src/main.py" in names
        assert "src/utils.js" in names


def test_archive_none_root(mock_project):
    """Verify that root_dir=None defaults to filename only."""
    f1 = mock_project / "src" / "main.py"
    output_zip = mock_project / "test_no_root.zip"
    
    res = FileOps.archive_selection([str(f1)], str(output_zip), root_dir=None)
    
    with zipfile.ZipFile(res, 'r') as z:
        names = z.namelist()
        assert "main.py" in names


def test_archive_empty_list(mock_project):
    """Verify empty selection creates a valid but empty zip."""
    output_zip = mock_project / "empty.zip"
    res = FileOps.archive_selection([], str(output_zip), root_dir=str(mock_project))
    assert os.path.exists(res)
    with zipfile.ZipFile(res, 'r') as z:
        assert len(z.namelist()) == 0
