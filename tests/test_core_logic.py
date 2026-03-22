import pytest
import pathlib
import os
from core_logic import search_generator, FileUtils

@pytest.mark.parametrize("query, mode, inverse, case, expected_names", [
    # 1. Smart Search (default, case-insensitive)
    ("MAIN", "smart", False, False, ["main.py"]),
    # 2. Exact Search (case-insensitive)
    ("main.py", "exact", False, False, ["main.py"]),
    # 3. Exact Search (case-sensitive)
    ("MAIN.PY", "exact", False, True, []), # Should not match
    # 4. Regex Search
    (r"utils\..*", "regex", False, False, ["utils.js"]),
    # 5. Content Search
    ("print", "content", False, False, ["main.py", "utils.js"]),
    # 6. Inverse Name Match
    ("main", "smart", True, False, ["utils.js", "config.json", "data.bin"]),
    # 7. Inverse Content Match
    ("print", "content", True, False, ["config.json"]),
])
def test_search_permutations(mock_project, query, mode, inverse, case, expected_names):
    results = list(search_generator(
        mock_project, query, mode, "", 
        is_inverse=inverse, case_sensitive=case
    ))
    result_names = [os.path.basename(r["path"]) for r in results]
    
    # Check if all expected names are in results
    for name in expected_names:
        assert name in result_names
    
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
