import pytest
import pathlib
import os
import zipfile
from unittest.mock import patch
from core_logic import search_generator, FileUtils, PathValidator, ContextFormatter, FileOps, FormatUtils, ActionBridge

@pytest.mark.parametrize("query, mode, inverse, case, inc_dirs, use_git, expected_names", [
    # 1. Smart Search (default, case-insensitive)
    ("MAIN", "smart", False, False, False, True, ["main.py"]),
    # 2. Exact Search (case-insensitive)
    ("main.py", "exact", False, False, False, True, ["main.py"]),
    # 3. Exact Search (case-sensitive)
    ("MAIN.PY", "exact", False, True, False, True, []), # Should not match
    # 4. Regex Search
    (r"utils\..*", "regex", False, False, False, True, ["utils.js"]),
    # 5. Content Search
    ("print", "content", False, False, False, True, ["main.py", "utils.js"]),
    # 6. Inverse Name Match
    ("main", "smart", True, False, False, True, ["utils.js", "config.json", "data.bin"]),
    # 7. Gitignore bypass (Search ignoring gitignore)
    ("error", "smart", False, False, False, False, ["error.log"]),
    # 8. Include Directories
    ("src", "smart", False, False, True, True, ["src"]),
])
def test_search_permutations(mock_project, query, mode, inverse, case, inc_dirs, use_git, expected_names):
    results = list(search_generator(
        mock_project, query, mode, "", 
        include_dirs=inc_dirs,
        is_inverse=inverse, 
        case_sensitive=case,
        use_gitignore=use_git
    ))
    result_names = [os.path.basename(r["path"]) for r in results]
    
    for name in expected_names:
        assert any(name in rn for rn in result_names), f"Expected {name} not found in {result_names}"

def test_metadata_accuracy(mock_project):
    """Verifies that the returned metadata matches the actual file properties."""
    results = list(search_generator(mock_project, "main.py", "exact", ""))
    assert len(results) == 1
    meta = results[0]
    
    path_obj = pathlib.Path(meta["path"])
    assert meta["size"] == path_obj.stat().st_size
    assert meta["mtime"] == path_obj.stat().st_mtime
    assert meta["ext"] == ".py"

def test_path_validator_is_relative_to_comprehensive(mock_project):
    """Verify robust path traversal defense."""
    root = str(mock_project.resolve())
    # Safe
    assert PathValidator.is_safe(str(mock_project / "src"), root) is True
    # Unsafe: Parent traversal
    assert PathValidator.is_safe(str(mock_project / ".." / "outside"), root) is False
    # Unsafe: Fake Prefix
    fake_root = str(mock_project.parent / (mock_project.name + "_fake"))
    assert PathValidator.is_safe(fake_root, root) is False
    # Unsafe: Absolute system path
    assert PathValidator.is_safe("C:/Windows" if os.name == 'nt' else "/etc", root) is False

def test_action_bridge_injection_and_quoting(mock_project):
    """Verify shell injection prevention across platforms."""
    test_file = mock_project / "src" / "main.py"
    # Malicious injection attempt
    malicious_template = "echo {name} ; touch " + str(mock_project / "injected.txt")
    res = ActionBridge.execute_tool(malicious_template, str(test_file), mock_project)
    assert not os.path.exists(mock_project / "injected.txt")

    # Special characters handling
    special_name = "test & $(whoami).txt"
    special_file = mock_project / special_name
    special_file.touch()
    res = ActionBridge.execute_tool("echo {name}", str(special_file), mock_project)
    assert special_name in res["stdout"]

def test_file_utils_batch_scan_logic(mock_project):
    """Verify the 'Stage All' scanning logic respects ignores."""
    # Recursive mode
    items = FileUtils.get_project_items(str(mock_project), ["*.js"], use_gitignore=True, mode="files")
    item_names = [os.path.basename(i) for i in items]
    assert "main.py" in item_names
    assert "utils.js" not in item_names # Excluded manually
    assert "error.log" not in item_names # Excluded by gitignore
    
    # Top-folders mode
    items_top = FileUtils.get_project_items(str(mock_project), [], use_gitignore=True, mode="top_folders")
    item_names_top = [os.path.basename(i) for i in items_top]
    assert "src" in item_names_top
    assert "main.py" not in item_names_top # Only top items

def test_data_manager_alignment_and_persistence(clean_config):
    dm = clean_config
    import json
    test_path = str(pathlib.Path("/fake/proj").resolve())
    with open(dm.config_path, 'w') as f:
        json.dump({"projects": {test_path: {"excludes": ".git"}}}, f)
    
    dm.load()
    proj_data = dm.get_project_data(test_path)
    assert "staging_list" in proj_data
    assert proj_data["excludes"] == ".git"
    
    dm.batch_stage(test_path, ["/p1", "/p2"])
    dm.save()
    with open(dm.config_path, 'r') as f:
        saved = json.load(f)
        assert "/p1" in saved["projects"][test_path]["staging_list"]

def test_data_manager_concurrency_stress(clean_config, mock_project):
    """Verify singleton thread safety and data integrity."""
    import threading
    dm = clean_config
    p = str(mock_project)
    def worker(i): dm.update_project_settings(p, {f"k{i}": i})
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()
    data = dm.get_project_data(p)
    assert all(data[f"k{i}"] == i for i in range(50))

def test_file_ops_unit_enhanced(mock_project):
    # Test Create & Error
    new_f = FileOps.create_item(str(mock_project), "unit.txt", is_dir=False)
    assert os.path.exists(new_f)
    with pytest.raises(FileExistsError):
        FileOps.create_item(str(mock_project), "unit.txt")

    # Test Archive
    zip_p = mock_project / "unit.zip"
    FileOps.archive_selection([new_f], str(zip_p), mock_project)
    assert os.path.exists(zip_p)