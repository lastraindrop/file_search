import pytest
import tkinter as tk
from unittest.mock import MagicMock, patch
import file_search
from file_search import FileCortexApp

class MockDataManager:
    """A lightweight version of DataManager that doesn't touch the real disk."""
    def __init__(self):
        self.data = {"projects": {}, "last_directory": None}
        self.save = MagicMock()
    
    def get_project_data(self, path):
        # Match the normalization used in the real app
        from file_cortex_core import PathValidator
        path_key = PathValidator.norm_path(path)
        if path_key not in self.data["projects"]:
            self.data["projects"][path_key] = {"staging_list": []}
        return self.data["projects"][path_key]

@pytest.fixture(scope="module")
def tk_root():
    """Provides a hidden real tkinter root for component testing."""
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()

@patch('file_search.DataManager', new=MockDataManager)
@patch('pathlib.Path.exists', return_value=True)
def test_staging_list_isolation(mock_exists, tk_root):
    """
    Test that FileCortexApp.staging_files and DataManager's config
    do NOT share the same list instance (Isolation Test).
    """
    with patch('pathlib.Path.stat') as mock_stat:
        # Mock stat to return a real-looking object with st_size and st_mode
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = 1024
        mock_stat_val.st_mode = 0o100644 # Regular file mode
        mock_stat.return_value = mock_stat_val
        
        # 1. Setup
        app = FileCortexApp(tk_root)
        
        p_str = "c:/test_project/test.txt"
        project_path = "c:/test_project"
        app.current_proj_config = app.data_mgr.get_project_data(project_path)
        app.current_proj_config["staging_list"] = [p_str]
        
        # 2. Simulate Refresh (Loading from config to UI)
        app.refresh_staging_ui()
        
        # 3. CRITICAL CHECK: Isolation
        old_id = id(app.current_proj_config["staging_list"])
        app.staging_files.clear()
        
        # Config list should STILL have the file and DIFFERENT ID!
        assert len(app.current_proj_config["staging_list"]) == 1
        assert id(app.staging_files) != old_id

@patch('file_search.DataManager', new=MockDataManager)
@patch('pathlib.Path.exists', return_value=True)
def test_remove_selection_isolation(mock_exists, tk_root):
    """
    Test that removing items via UI update doesn't pollute the config with a shared reference.
    """
    app = FileCortexApp(tk_root)
    
    project_path = "C:/test_project"
    app.current_proj_config = app.data_mgr.get_project_data(project_path)
    
    # Add files to UI local cache
    app.staging_files = ["c:/f1.txt", "c:/f2.txt"]
    # Mock Treeview items
    app.tree_staging = MagicMock()
    app.tree_staging.selection.return_value = []
    
    # Simulate a "Save to config" operation
    app.remove_staging_selection()
    
    # 4. CRITICAL CHECK: Mutation after save
    config_list = app.current_proj_config["staging_list"]
    assert id(app.staging_files) != id(config_list)
    
    app.staging_files.append("c:/f3.txt")
    assert "c:/f3.txt" not in config_list

if __name__ == "__main__":
    pytest.main([__file__])
