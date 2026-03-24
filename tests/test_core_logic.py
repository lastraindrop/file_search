import pytest
import pathlib
import os
import zipfile
from unittest.mock import patch
from core_logic import search_generator, FileUtils, PathValidator, ContextFormatter, FileOps

@pytest.mark.parametrize("query, mode, inverse, case, inc_dirs, expected_names", [
    # 1. Smart Search (default, case-insensitive)
    ("MAIN", "smart", False, False, False, ["main.py"]),
    # 2. Exact Search (case-insensitive)
    ("main.py", "exact", False, False, False, ["main.py"]),
    # 3. Exact Search (case-sensitive)
    ("MAIN.PY", "exact", False, True, False, []), # Should not match
    # 4. Regex Search
    (r"utils\..*", "regex", False, False, False, ["utils.js"]),
    # 5. Content Search
    ("print", "content", False, False, False, ["main.py", "utils.js"]),
    # 6. Inverse Name Match
    ("main", "smart", True, False, False, ["utils.js", "config.json", "data.bin"]),
    # 7. Inverse Content Match
    ("print", "content", True, False, False, ["config.json"]),
    # 8. Include Directories
    ("src", "smart", False, False, True, ["src"]),
    # 9. Smart Search with spaces (AND logic)
    ("utils js", "smart", False, False, False, ["utils.js"]),
])
def test_search_permutations(mock_project, query, mode, inverse, case, inc_dirs, expected_names):
    results = list(search_generator(
        mock_project, query, mode, "", 
        include_dirs=inc_dirs,
        is_inverse=inverse, 
        case_sensitive=case
    ))
    result_names = [os.path.basename(r["path"]) for r in results]
    
    # Check if all expected names are in results (Dynamic Check)
    for name in expected_names:
        assert any(name in rn for rn in result_names), f"Expected {name} not found in {result_names}"
    
    # Check if results are correctly restricted
    if not inverse and mode != 'content':
        assert len(results) == len(expected_names)

def test_metadata_accuracy(mock_project):
    """Verifies that the returned metadata matches the actual file properties."""
    results = list(search_generator(mock_project, "main.py", "exact", ""))
    assert len(results) == 1
    meta = results[0]
    
    path_obj = pathlib.Path(meta["path"])
    assert meta["size"] == path_obj.stat().st_size
    assert meta["mtime"] == path_obj.stat().st_mtime
    assert meta["ext"] == ".py"

def test_gitignore_complex(mock_project):
    """Verifies ignore logic with multiple patterns."""
    # error.log is in gitignore
    results = list(search_generator(mock_project, "error", "smart", ""))
    assert len(results) == 0
    
    # node_modules is in gitignore
    results = list(search_generator(mock_project, "node_modules", "smart", "", include_dirs=True))
    assert not any("node_modules" in r["path"] for r in results)

def test_manual_excludes(mock_project):
    """Verifies that manual excludes string works."""
    # Exclude .js files manually
    results = list(search_generator(mock_project, "", "smart", "*.js"))
    paths = [r["path"] for r in results]
    assert not any(p.endswith(".js") for p in paths)

def test_binary_file_detection(mock_project):
    """Content search should skip binary files."""
    # data.bin contains 'hello' (binary)
    results = list(search_generator(mock_project, "hello", "content", ""))
    # Should not find it because it's binary
    assert not any("data.bin" in r["path"] for r in results)

# --- New Unit Tests for Latest Architecture ---

def test_path_validator_safety(mock_project):
    root = mock_project
    safe_path = root / "src" / "main.py"
    unsafe_path = root / ".." / "outside.txt"
    
    assert PathValidator.is_safe(str(safe_path), str(root)) is True
    assert PathValidator.is_safe(str(unsafe_path), str(root)) is False
    assert PathValidator.is_safe("C:/Windows/system32", str(root)) is False

def test_context_formatter_markdown(mock_project):
    paths = [str(mock_project / "src" / "main.py"), str(mock_project / "image.png")]
    md = ContextFormatter.to_markdown(paths, mock_project)
    
    # Use normalized path for cross-platform check
    expected_rel = os.path.relpath(mock_project / "src" / "main.py", mock_project)
    assert f"File: {expected_rel}" in md
    assert "print('hello')" in md
    assert "```python" in md
    
    # Should skip binary image.png
    assert "image.png" not in md

def test_file_ops_unit(mock_project):
    # Test Create
    new_f = FileOps.create_item(str(mock_project), "test_create.txt", is_dir=False)
    assert os.path.exists(new_f)
    assert pathlib.Path(new_f).is_file()
    
    new_d = FileOps.create_item(str(mock_project), "test_dir", is_dir=True)
    assert os.path.exists(new_d)
    assert pathlib.Path(new_d).is_dir()
    
    # Test Duplicate Error
    with pytest.raises(FileExistsError):
        FileOps.create_item(str(mock_project / "src"), "main.py")

def test_archive_selection_logic(mock_project):
    paths = [str(mock_project / "src" / "main.py")]
    zip_path = mock_project / "test.zip"
    
    result = FileOps.archive_selection(paths, str(zip_path), mock_project)
    assert os.path.exists(result)
    
    with zipfile.ZipFile(result, 'r') as z:
        names = z.namelist()
        assert "src/main.py" in names

def test_generate_ascii_tree_depth(mock_project):
    """Verifies that the tree generation respects max_depth."""
    base = mock_project / "deep"
    base.mkdir()
    curr = base
    for i in range(20):
        curr = curr / f"level_{i}"
        curr.mkdir()
    
    # Test with default limit (15)
    tree = FileUtils.generate_ascii_tree(mock_project, "")
    assert "level_14" in tree
    assert "[Max Depth Reached (15) ...]" in tree
    assert "level_16" not in tree

def test_search_engine_parallel_stress(stress_project):
    """Verify concurrent search engine stability and correctness under load."""
    query = "keyword_target_5"
    results = list(search_generator(stress_project, query, "content", ""))
    
    # We expect 10 matches (one in each of the 10 dirs)
    assert len(results) == 10
    for r in results:
        assert "file_5.txt" in r["path"]
        assert r["match_type"] == "Content Match"

def test_data_manager_alignment_logic():
    """Test automatic schema detection and alignment for old config files."""
    from core_logic import DataManager, CONFIG_FILE
    import json
    import tempfile
    import shutil
    
    tmp_d = tempfile.mkdtemp()
    tmp_path = pathlib.Path(tmp_d)
    try:
        # 1. Create a "vOld" config missing new fields
        old_config = {
            "last_directory": str(tmp_path),
            "projects": {
                str(tmp_path): {
                    "excludes": ".git"
                }
            }
        }
        test_config_file = tmp_path / "test_config_data.json"
        test_config_file.write_text(json.dumps(old_config))
        
        # 2. Mock CONFIG_FILE and load
        with patch('core_logic.CONFIG_FILE', test_config_file):
            dm = DataManager()
            proj_data = dm.get_project_data(str(tmp_path))
            
            # 3. Verify Alignment
            assert "sessions" in proj_data
            assert "notes" in proj_data
            assert "tags" in proj_data
            assert proj_data["excludes"] == ".git"
            
            # 4. Verify Persistence
            dm.save()
            with open(test_config_file, 'r') as f:
                saved_data = json.load(f)
                assert "sessions" in saved_data["projects"][str(tmp_path)]
    finally:
        shutil.rmtree(tmp_d, ignore_errors=True)

@patch('core_logic.logger')
def test_search_generator_error_handling(mock_logger, mock_project):
    """Verify that the engine handles permission errors gracefully during walk."""
    with patch('os.scandir', side_effect=PermissionError("Mock Permission Denied")):
        results = list(search_generator(mock_project, "main", "smart", ""))
        # Should not crash, just yield nothing or stop gracefully
        assert len(results) == 0
