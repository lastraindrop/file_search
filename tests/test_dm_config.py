import os
import pathlib
import threading

import pytest

from file_cortex_core import DataManager, PathValidator

# -----------------------------------------------------------------------------
# 1. Singleton & Initialization
# -----------------------------------------------------------------------------

def test_dm_singleton_and_defaults(clean_config):
    """Verify DataManager singleton residency and default schema."""
    dm = clean_config
    dm2 = DataManager()
    assert dm is dm2
    assert "global_settings" in dm.data
    assert isinstance(dm.data["projects"], dict)

def test_core_exports_include_get_app_dir():
    """Public package exports should include get_app_dir consistently."""
    import file_cortex_core

    assert hasattr(file_cortex_core, "get_app_dir")
    assert isinstance(file_cortex_core.get_app_dir(), pathlib.Path)

# -----------------------------------------------------------------------------
# 2. Persistence Symmetry & Atomicity (C3)
# -----------------------------------------------------------------------------

def test_dm_save_load_symmetry(clean_config, mock_project):
    """C3: Verify that complex project settings persist across reloads."""
    dm = clean_config
    p_str = str(mock_project)
    dm.update_project_settings(p_str, {"excludes": "*.log *.bak", "max_search_size_mb": 99})
    dm.save()

    # Re-instantiate
    DataManager._instance = None
    dm_new = DataManager()
    dm_new.config_path = dm.config_path
    dm_new.load()

    proj = dm_new.get_project_data(p_str)
    assert proj["excludes"] == "*.log *.bak"
    assert proj["max_search_size_mb"] == 99

def test_dm_save_concurrency_stress(clean_config, mock_project):
    """Verify lock integrity under concurrent save load."""
    dm = clean_config
    p = str(mock_project)

    def worker(i):
        # Whitelisted keys update
        dm.update_project_settings(p, {"search_settings": {"q": i}})
        dm.save()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Reload and ensure not corrupted
    dm.load()
    assert len(dm.data["projects"]) >= 1

# -----------------------------------------------------------------------------
# 3. Project Ops (Groups, Favorites, categories)
# -----------------------------------------------------------------------------

def test_dm_group_management(clean_config, mock_project):
    """Consolidated: Add -> Remove -> List logic for favorite groups."""
    dm = clean_config
    p = str(mock_project)
    # C1 Critical: Pass absolute paths to ensure norm_path resolves to the correct project location
    files = [str(mock_project / "src" / "main.py"), str(mock_project / "README.md")]

    # Add
    dm.add_to_group(p, "Default", files)
    proj = dm.get_project_data(p)
    assert len(proj["groups"]["Default"]) == 2

    # Remove
    dm.remove_from_group(p, "Default", [files[0]])
    assert len(proj["groups"]["Default"]) == 1
    # Check with normalization
    found = [PathValidator.norm_path(x) for x in proj["groups"]["Default"]]
    assert PathValidator.norm_path(files[1]) in found

def test_dm_categorizer_logic(clean_config, mock_project):
    """Verify quick categories validation."""
    dm = clean_config
    p = str(mock_project)
    with pytest.raises(ValueError):
        # Traversal check
        dm.update_quick_categories(p, {"Evil": "../../etc"})

    dm.update_quick_categories(p, {"Logs": "logs"})
    assert dm.get_project_data(p)["quick_categories"]["Logs"] == "logs"

# -----------------------------------------------------------------------------
# 4. Global Settings & History
# -----------------------------------------------------------------------------

def test_dm_global_settings_and_history(clean_config, mock_project):
    """Consolidated: History tracking and global settings update."""
    dm = clean_config
    p_path = PathValidator.norm_path(str(mock_project / "another_proj"))
    if not os.path.exists(p_path):
        os.makedirs(p_path, exist_ok=True)

    dm.add_to_recent(p_path)
    found_recent = [PathValidator.norm_path(x) for x in dm.data["recent_projects"]]
    assert p_path in found_recent

    # Global settings update
    dm.update_global_settings({"preview_limit_mb": 4.0})
    assert dm.data["global_settings"]["preview_limit_mb"] == 4.0
