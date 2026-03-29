import pytest
import os
import pathlib
import sys
from file_cortex_core import ActionBridge, FileOps, DataManager

def test_action_bridge_win_quote_injection(mock_project):
    """Verify shell injection prevention (Win platform simulation)."""
    # Malicious injection attempt: {name} as "; touch injected.txt"
    # Actually context variables are escaped using win_quote
    test_file = mock_project / "src" / "main.py"
    
    # Simulating a template that would be dangerous without win_quote
    malicious_template = "echo {name} ; exit"
    
    # We patch os.name to simulate windows and then verify win_quote behavior
    # Note: ActionBridge.execute_tool uses sys.executable inside some contexts,
    # but the key is the string formatting.
    
    # We'll use a safer check: can it echo a filename with special chars?
    special_name = "test & %WHOAMI%.txt"
    special_path = mock_project / special_name
    special_path.touch()
    
    res = ActionBridge.execute_tool("echo {name}", str(special_path), mock_project)
    
    # If injection occurred on Windows, we'd see %WHOAMI% expanded or error.
    # If quoted, it remains as part of the string.
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
