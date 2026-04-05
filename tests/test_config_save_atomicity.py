"""
CR-B04: Verify that save() uses unique temp file names and handles concurrency.
"""
import pytest
import os
import threading
import json
from unittest.mock import patch
from file_cortex_core import DataManager


def test_concurrent_save_integrity(clean_config, mock_project):
    """Verify that multiple concurrent saves don't cause data corruption."""
    dm = clean_config
    p = str(mock_project)
    
    # Pre-populate project
    dm.get_project_data(p)
    
    def worker(i):
        # Update search_settings (now whitelisted in MUTABLE_SETTINGS)
        dm.update_project_settings(p, {"search_settings": {"last_query": f"q_{i}"}})
        dm.save()
        
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    # Reload and check 
    with open(dm.config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        assert data["projects"] is not None


def test_temp_file_cleanup_on_error(clean_config):
    """Verify that temporary files are cleaned up if disk write fails."""
    dm = clean_config
    # Use json.dump because it's guaranteed to be called inside the with block
    with patch('json.dump', side_effect=IOError("Disk Full")):
        with pytest.raises(IOError):
            dm.save()
            
    # Check if any .tmp files are left over in the config directory
    config_dir = dm.config_path.parent
    tmp_files = [f for f in os.listdir(config_dir) if f.endswith('.tmp')]
    assert len(tmp_files) == 0


def test_save_load_symmetry(clean_config, mock_project):
    """Verify that data written is exactly what we read back."""
    dm = clean_config
    p = dm.config_path.parent / "test_proj"
    p.mkdir()
    
    # Set complex data
    dm.update_project_settings(str(p), {"excludes": "*.log *.tmp", "max_search_size_mb": 42})
    dm.save()
    
    # Reset singleton to force reload
    DataManager._instance = None
    dm2 = DataManager()
    dm2.config_path = dm.config_path
    dm2.load()
    
    from file_cortex_core import PathValidator
    norm_p = PathValidator.norm_path(str(p))
    proj = dm2.get_project_data(norm_p)
    assert proj["excludes"] == "*.log *.tmp"
    assert proj["max_search_size_mb"] == 42
