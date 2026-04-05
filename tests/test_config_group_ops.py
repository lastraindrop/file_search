"""
CR-C04: Verify that remove_from_group correctly normalizes paths to 
ensure symmetric behavior with add_to_group.
"""
import pytest
import pathlib
from file_cortex_core import DataManager, PathValidator


def test_add_remove_case_symmetry(clean_config, mock_project):
    """Verify that removing with different case works if it normalizes."""
    dm = clean_config
    p = str(mock_project)
    raw_path = str(mock_project / "src" / "Main.py") # Upper case for test
    
    # 1. Add (it will normalize)
    dm.add_to_group(p, "TestGroup", [raw_path])
    proj = dm.get_project_data(p)
    norm_path = PathValidator.norm_path(raw_path)
    assert norm_path in proj["groups"]["TestGroup"]
    
    # 2. Remove using lowercase (different from norm if drive letter case varies, etc.)
    # In Windows, norm_path lowercases. So we test by sending a different case again.
    dm.remove_from_group(p, "TestGroup", [raw_path.upper()])
    proj = dm.get_project_data(p)
    assert norm_path not in proj["groups"]["TestGroup"]


def test_add_idempotent(clean_config, mock_project):
    """Verify that adding the same file twice doesn't duplicate."""
    dm = clean_config
    p = str(mock_project)
    path = str(mock_project / "src" / "main.py")
    
    dm.add_to_group(p, "TestGroup", [path])
    dm.add_to_group(p, "TestGroup", [path])
    
    proj = dm.get_project_data(p)
    assert proj["groups"]["TestGroup"].count(PathValidator.norm_path(path)) == 1


def test_remove_from_nonexistent_group(clean_config, mock_project):
    """Verify that removing from non-existent group doesn't raise error."""
    dm = clean_config
    p = str(mock_project)
    dm.remove_from_group(p, "GhostGroup", ["/any/path"]) or True


def test_group_survives_empty(clean_config, mock_project):
    """Verify that a group remains in dict even after being emptied."""
    dm = clean_config
    p = str(mock_project)
    path = str(mock_project / "src" / "main.py")
    
    dm.add_to_group(p, "TestGroup", [path])
    dm.remove_from_group(p, "TestGroup", [path])
    
    proj = dm.get_project_data(p)
    assert "TestGroup" in proj["groups"]
    assert len(proj["groups"]["TestGroup"]) == 0
