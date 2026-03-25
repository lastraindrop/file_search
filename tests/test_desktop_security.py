import pytest
from unittest.mock import MagicMock, patch
import pathlib
import os
from file_search import FileCortexApp
import tkinter as tk

@pytest.fixture
def app_instance():
    root = tk.Tk()
    # Mocking DataManager to avoid config loading issues
    with patch('file_search.DataManager') as mock_dm:
        mock_dm.return_value.data = {"last_directory": "", "projects": {}}
        app = FileCortexApp(root)
        yield app
    root.destroy()

def test_powershell_injection_prevention(app_instance):
    """
    Verifies that ctx_copy_file_to_os uses a secure list-based subprocess call
    instead of string concatenation.
    """
    # 1. Setup mock paths and tree selection
    mock_path = pathlib.Path("C:/MyProject/normal.txt")
    evil_path = pathlib.Path("C:/MyProject/test'; echo 'Pwned';'.txt")
    
    app_instance.active_tree = MagicMock()
    app_instance.active_tree.selection.return_value = ["item1", "item2"]
    
    # Mock _get_ctx_paths to return our test paths
    app_instance._get_ctx_paths = MagicMock(return_value=[mock_path, evil_path])
    
    # 2. Patch subprocess.run
    with patch('subprocess.run') as mock_run:
        app_instance.ctx_copy_file_to_os()
        
        # 3. Assertions
        assert mock_run.called
        args, kwargs = mock_run.call_args
        
        # Check that the first argument is a LIST (secure)
        cmd_list = args[0]
        assert isinstance(cmd_list, list)
        
        # Check that it uses powershell -Command and $args
        assert "powershell" in cmd_list
        assert "Set-Clipboard -Path $args" in cmd_list
        
        # Check that file paths are passed as separate arguments
        assert str(mock_path) in cmd_list
        assert str(evil_path) in cmd_list
        
        # Ensure shell=True is NOT used
        assert kwargs.get('shell') is not True
