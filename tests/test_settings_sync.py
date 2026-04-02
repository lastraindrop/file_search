import pytest
import os
from file_cortex_core.config import DataManager
from file_cortex_core.security import PathValidator

def test_project_settings_persistence(clean_config):
    dm = clean_config
    project_path = PathValidator.norm_path(".")
    
    # 1. Update settings
    proj_data = dm.get_project_data(project_path)
    proj_data["excludes"] = "*.test_sync"
    proj_data["search_settings"] = {
        "mode": "regex", 
        "case_sensitive": True,
        "inverse": False,
        "include_dirs": False
    }
    dm.save()
    
    # 2. Force Reload and verify
    dm.load() 
    refreshed_data = dm.get_project_data(project_path)
    assert refreshed_data["excludes"] == "*.test_sync"
    assert refreshed_data["search_settings"]["mode"] == "regex"
    assert refreshed_data["search_settings"]["case_sensitive"] is True

def test_default_schema_alignment(clean_config):
    dm = clean_config
    # Create a project entry with missing fields to simulate old config version
    path = PathValidator.norm_path("legacy_project")
    dm.data["projects"][path] = {"excludes": "old_style"} 
    
    # get_project_data should auto-patch missing fields from DEFAULT_SCHEMA
    proj = dm.get_project_data(path)
    assert "search_settings" in proj
    assert proj["search_settings"]["mode"] == "smart"
    assert "prompt_templates" in proj
