import pytest
import os
import threading
from file_cortex_core.actions import ActionBridge
from file_cortex_core.config import DataManager

def test_actionbridge_percent_injection(mock_project):
    """Verify % injection check when shell=True on Windows"""
    if os.name != 'nt':
        pytest.skip("Test only applicable on Windows")
    test_file = mock_project / "test_%PATH%.txt"
    test_file.touch()
    
    # Should NOT raise ValueError anymore, but return escaped string
    cmd, is_shell, ctx = ActionBridge._prepare_execution("echo {name} & echo ok", str(test_file), str(mock_project))
    assert is_shell is True
    assert "%%PATH%%" in cmd 

def test_datamanager_concurrent_mutations(clean_config, mock_project):
    dm = DataManager()
    proj_path = str(mock_project)
    dm.get_project_data(proj_path) # ensure init
    
    def updater_thread():
        for i in range(100):
            dm.update_project_settings(proj_path, {"max_search_size_mb": 100 + i})
            
    def tagger_thread():
        for i in range(100):
            dm.add_tag(proj_path, "file.txt", f"tag_{i}")
            
    def saver_thread():
        for _ in range(50):
            dm.save()
            
    t1 = threading.Thread(target=updater_thread)
    t2 = threading.Thread(target=tagger_thread)
    t3 = threading.Thread(target=saver_thread)
    
    t1.start()
    t2.start()
    t3.start()
    
    t1.join()
    t2.join()
    t3.join()
    
    # Should run without RuntimeError
    assert dm.get_project_data(proj_path)["max_search_size_mb"] >= 100