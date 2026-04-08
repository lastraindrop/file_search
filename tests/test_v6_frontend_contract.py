import pytest
import pydantic
from typing import List, Dict, Any

def test_api_children_schema_contract(project_client, mock_project):
    """Verify that /api/fs/children returns the exact structure expected by Premium UI."""
    res = project_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res.status_code == 200
    data = res.json()
    
    assert "parent" in data
    assert "children" in data
    assert isinstance(data["children"], list)
    
    if data["children"]:
        child = data["children"][0]
        # Mandatory fields for UI rendering
        expected_keys = {"name", "path", "type", "size", "size_fmt", "mtime", "mtime_fmt", "has_children"}
        for key in expected_keys:
            assert key in child, f"Missing key '{key}' in child item: {child.keys()}"
            
        # Type & Format checks
        assert isinstance(child["has_children"], bool)
        assert isinstance(child["size"], int)
        assert child["type"] in ("file", "dir")
        # Premium UI expects formatted strings
        assert isinstance(child["size_fmt"], str)
        assert isinstance(child["mtime_fmt"], str)

def test_api_config_schema_contract(project_client, mock_project):
    """Verify that /api/project/config exposes all necessary UI settings."""
    res = project_client.get(f"/api/project/config?path={str(mock_project)}")
    assert res.status_code == 200
    config = res.json()
    
    required_sections = {
        "excludes", "staging_list", "custom_tools", "quick_categories", 
        "prompt_templates", "search_settings", "token_threshold"
    }
    for section in required_sections:
        assert section in config, f"Missing configuration section '{section}'"
        
    assert isinstance(config["staging_list"], list)
    assert isinstance(config["custom_tools"], dict)
    assert isinstance(config["quick_categories"], dict)

def test_api_open_response_contract(project_client, mock_project):
    """Verify /api/open response contains name and path for UI breadcrumbs."""
    from file_cortex_core import PathValidator
    res = project_client.post("/api/open", json={"path": str(mock_project)})
    data = res.json()
    
    assert data["path"] == PathValidator.norm_path(mock_project)
    # Note: data["name"] might be lowercase if path was neutralized
    assert data["name"].lower() == mock_project.name.lower()
    assert "size_fmt" in data

def test_api_content_response_truncation_flag(project_client, mock_project):
    """Verify that /api/content provides a truncation flag and encoding info for UI."""
    res = project_client.get(f"/api/content?path={str(mock_project / 'src' / 'main.py')}")
    data = res.json()
    assert "content" in data
    assert isinstance(data["content"], str)
    assert "encoding" in data
    assert "is_truncated" in data
