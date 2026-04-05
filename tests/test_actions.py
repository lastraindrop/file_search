import pytest
import os
import pathlib
import sys
from file_cortex_core import ActionBridge, FileOps, DataManager

@pytest.mark.parametrize("template, expected_in_out", [
    ("echo {name}", "main.py"),
    ("echo {ext}", ".py"),
    ("echo {parent_name}", "src"),
])
def test_action_bridge_variable_expansion(mock_project, template, expected_in_out):
    """Verify that {name}, {ext}, {parent_name} variables are expanded correctly."""
    test_file = mock_project / "src" / "main.py"
    res = ActionBridge.execute_tool(template, str(test_file), str(mock_project))
    # We use lower() to handle Windows case-insensitivity in paths
    assert expected_in_out.lower() in res["stdout"].lower()

def test_action_bridge_win_quote_injection(mock_project):
    """Verify shell injection prevention (Win platform simulation)."""
    special_name = "test & %WHOAMI%.txt"
    special_path = mock_project / special_name
    special_path.touch()
    
    res = ActionBridge.execute_tool("echo {name}", str(special_path), mock_project)
    
    import os
    if os.name == 'nt':
        # On Windows CMD, if % is present, we now strictly block it to prevent injection
        assert "error" in res["status"]
        assert "Command injection risk" in res["error"]
    else:
        assert special_name in res["stdout"]

def test_file_ops_crud_lifecycle(mock_project):
    """Verify full CRUD lifecycle for FileOps."""
    root = str(mock_project)
    
    # 1. Create file
    f_path_str = FileOps.create_item(root, "crud_test.txt", is_dir=False)
    assert os.path.exists(f_path_str)
    
    # 2. Save content
    content = "Hello Actions!"
    FileOps.save_content(f_path_str, content)
    assert pathlib.Path(f_path_str).read_text(encoding='utf-8') == content
    
    # 3. Rename
    renamed_path_str = FileOps.rename_file(f_path_str, "crud_final.txt")
    assert "crud_final.txt" in renamed_path_str
    assert not os.path.exists(f_path_str)
    assert os.path.exists(renamed_path_str)
    
    # 4. Delete
    FileOps.delete_file(renamed_path_str)
    assert not os.path.exists(renamed_path_str)

def test_file_ops_batch_categorize(mock_project):
    """Verify batch categorization (moving to classified folders)."""
    dm = DataManager()
    root = str(mock_project)
    p_config = dm.get_project_data(root)
    p_config["quick_categories"] = {"JS": "scripts/javascript"}
    dm.save()
    
    js_file = mock_project / "src" / "utils.js"
    moved = FileOps.batch_categorize(root, [str(js_file)], "JS")
    
    assert len(moved) == 1
    assert "scripts" in moved[0] and "javascript" in moved[0]
    assert os.path.exists(moved[0])
    assert not os.path.exists(js_file)

def test_file_ops_archive_logic(mock_project):
    """Verify ZIP archive creation for selected files."""
    f1 = mock_project / "f1.txt"
    f1.write_text("f1")
    output_zip = mock_project / "test_archive.zip"
    
    res = FileOps.archive_selection([str(f1)], str(output_zip), mock_project)
    
    assert os.path.exists(res)
    assert ".zip" in res
    
    import zipfile
    with zipfile.ZipFile(res, 'r') as z:
        assert "f1.txt" in z.namelist()

def test_stream_tool_nonexistent_path(mock_project):
    """Verify stream_tool returns error for missing file."""
    results = list(ActionBridge.stream_tool("echo {name}", "/nonexistent", mock_project))
    assert any("error" in r for r in results)
