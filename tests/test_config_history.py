from file_cortex_core.config import DataManager
from file_cortex_core.security import PathValidator

def test_workspace_history_logic():
    dm = DataManager()
    # Reset for test
    dm.data["recent_projects"] = []
    dm.data["pinned_projects"] = []
    
    # Test recent add
    path1 = PathValidator.norm_path("project1")
    dm.add_to_recent(path1)
    assert dm.data["recent_projects"][0] == path1
    
    path2 = PathValidator.norm_path("project2")
    dm.add_to_recent(path2)
    assert dm.data["recent_projects"][0] == path2
    assert dm.data["recent_projects"][1] == path1
    
    # Test move to top
    dm.add_to_recent(path1)
    assert dm.data["recent_projects"][0] == path1
    assert len(dm.data["recent_projects"]) == 2
    
    # Test pinning
    dm.toggle_pinned(path1)
    assert path1 in dm.data["pinned_projects"]
    
    dm.toggle_pinned(path1)
    assert path1 not in dm.data["pinned_projects"]

def test_workspaces_summary():
    dm = DataManager()
    # Mock some existing paths
    cur_dir = PathValidator.norm_path(".")
    dm.data["pinned_projects"] = [cur_dir]
    dm.data["recent_projects"] = [cur_dir, PathValidator.norm_path("..")]
    
    summary = dm.get_workspaces_summary()
    assert any(p["path"] == cur_dir for p in summary["pinned"])
    # cur_dir should not be in recent if it's in pinned
    assert not any(p["path"] == cur_dir for p in summary["recent"])
