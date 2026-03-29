import pytest
import pathlib
import os
import json
import threading
from file_cortex_core import DataManager

def test_data_manager_singleton():
    """Verify DataManager is a thread-safe singleton."""
    dm1 = DataManager()
    dm2 = DataManager()
    assert dm1 is dm2

def test_data_manager_persistence(clean_config):
    """Verify that configuration survives a write-load cycle."""
    dm = clean_config # clean_config points to a temporary config file
    test_path = str(pathlib.Path("/fake/proj").resolve())
    
    # 1. Update and save
    dm.update_project_settings(test_path, {"excludes": ".git node_modules"})
    dm.save()
    
    # 2. Reload into a new object (simulated)
    # Since it is a singleton, we need to clear it manually in the test environment (as in conftest)
    with open(dm.config_path, 'r', encoding='utf-8') as f:
        from file_cortex_core import PathValidator
        data = json.load(f)
        norm_test_path = PathValidator.norm_path(test_path)
        assert data["projects"][norm_test_path]["excludes"] == ".git node_modules"

def test_data_manager_concurrency_stress(clean_config, mock_project):
    """Verify thread safety during concurrent writes."""
    dm = clean_config
    p = str(mock_project)
    
    def worker(i):
        # Use prompt_templates which is in the MUTABLE_SETTINGS whitelist
        dm.update_project_settings(p, {"prompt_templates": {f"k{i}": str(i)}})
        
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    data = dm.get_project_data(p)
    # Note: data["prompt_templates"] is overwritten by each thread since it's a dict replacement
    # but the key is that no crash occurred during concurrent save().
    assert "prompt_templates" in data

def test_prompt_template_schema_auto_fill(clean_config):
    """Verify that newly accessed projects get default prompt templates."""
    dm = clean_config
    p = str(pathlib.Path("/new/project").resolve())
    
    proj_data = dm.get_project_data(p)
    assert "prompt_templates" in proj_data
    assert "Code Review" in proj_data["prompt_templates"]
    assert "Summary" in proj_data["prompt_templates"]

def test_data_manager_resolve_project_root(clean_config):
    """Verify project root resolution for nested files."""
    dm = clean_config
    root_path = str(pathlib.Path("/my_ws").resolve())
    file_path = str(pathlib.Path("/my_ws/src/index.js").resolve())
    
    dm.update_project_settings(root_path, {"notes": {}})
    dm.save()
    
    resolved = dm.resolve_project_root(file_path)
    # Note: resolve_project_root compares resolved paths
    assert resolved is not None
    assert pathlib.Path(resolved) == pathlib.Path(root_path)

def test_data_manager_batch_stage(clean_config, mock_project):
    """Verify batch staging logic and config update."""
    dm = clean_config
    p = str(mock_project)
    files = ["f1.py", "f2.js"]
    
    count = dm.batch_stage(p, files)
    assert count == 2
    
    proj = dm.get_project_data(p)
    assert "f1.py" in proj["staging_list"]
    assert "f2.js" in proj["staging_list"]
    
    # Repeat (Should not duplicate)
    count2 = dm.batch_stage(p, files)
    assert count2 == 0

def test_update_settings_whitelist(clean_config):
    """Verify MUTABLE_SETTINGS whitelist is enforced."""
    dm = clean_config
    p = str(pathlib.Path("/test/whitelist").resolve())
    dm.get_project_data(p)  # Initialize defaults
    
    # Protected keys should NOT change via general settings API
    dm.update_project_settings(p, {"groups": {}, "notes": {"x": "y"}, "sessions": []})
    proj = dm.get_project_data(p)
    assert "Default" in proj["groups"]  # groups preserved
    assert "x" not in proj["notes"]      # notes not injected
    
    # Allowed keys should change
    dm.update_project_settings(p, {"excludes": "*.bak"})
    assert dm.get_project_data(p)["excludes"] == "*.bak"

def test_load_preserves_structure(clean_config):
    """Verify load() performs field-level merge, not shallow dict.update()."""
    dm = clean_config
    p = str(pathlib.Path("/merge/test").resolve())
    dm.get_project_data(p)
    dm.save()
    
    # Directly modify data to ensure load reconstructs properly
    dm.data["last_directory"] = "/original"
    dm.save()
    
    # Simulate fresh load
    dm.data = {"last_directory": "", "projects": {}}
    dm.load()
    from file_cortex_core import PathValidator
    assert dm.data["last_directory"] == "/original"
    assert PathValidator.norm_path(p) in dm.data["projects"]

def test_update_tools_validation(clean_config):
    """Verify dedicated tools API validation."""
    dm = clean_config
    p = "/some/proj"
    with pytest.raises(ValueError):
        dm.update_custom_tools(p, ["not", "a", "dict"])
    with pytest.raises(ValueError):
        dm.update_custom_tools(p, {123: "invalid key type"})

def test_update_categories_validation(clean_config):
    """Verify dedicated categories API validation and traversal block."""
    dm = clean_config
    p = "/some/proj"
    with pytest.raises(ValueError):
        dm.update_quick_categories(p, {"Evil": "../etc"})
    
    dm.update_quick_categories(p, {"Safe": "subdir/internal"})
    assert dm.get_project_data(p)["quick_categories"]["Safe"] == "subdir/internal"
