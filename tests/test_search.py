import pytest
import os
import pathlib
from file_cortex_core import search_generator, FileUtils

@pytest.mark.parametrize("query, mode, inverse, case, inc_dirs, use_git, expected_names", [
    # --- Smart Scan Matrix ---
    ("MAIN", "smart", False, False, False, True, ["main.py"]),
    ("main py", "smart", False, False, False, True, ["main.py"]),
    ("MAIN", "smart", False, True, False, True, []), # Case-sensitive mis-match
    ("main", "smart", True, False, False, True, ["utils.js", "config.json", "data.bin"]), # Inverse
    
    # --- Exact Match Matrix ---
    ("main.py", "exact", False, False, False, True, ["main.py"]),
    ("MAIN.PY", "exact", False, True, False, True, []),
    (".js", "exact", False, False, False, True, ["utils.js"]),

    # --- Regex (Content-based) Matrix ---
    (r"console\..*", "regex", False, False, False, True, ["utils.js"]),
    (r"print\(.*", "regex", False, False, False, True, ["main.py"]),
    (r"NON_EXISTENT", "regex", False, False, False, True, []),

    # --- Content Search Matrix ---
    ("print", "content", False, False, False, True, ["main.py", "utils.js"]),
    ("console", "content", False, False, False, True, ["utils.js"]),
    ("non-existent-string", "content", False, False, False, True, []),
    
    # --- Gitignore & Ignores ---
    ("error", "smart", False, False, False, False, ["error.log"]), # Found with gitignore=False
    ("error", "smart", False, False, False, True, []),              # Ignored by default
    
    # --- Directory Inclusion ---
    ("src", "smart", False, False, True, True, ["src"]),
])
def test_search_generator_matrix(mock_project, query, mode, inverse, case, inc_dirs, use_git, expected_names):
    """
    Exhaustive search test covering all primary mode and parameter permutations.
    """
    results = list(search_generator(
        mock_project, query, mode, "", 
        include_dirs=inc_dirs,
        is_inverse=inverse, 
        case_sensitive=case,
        use_gitignore=use_git
    ))
    result_names = [os.path.basename(r["path"]) for r in results]
    
    if expected_names:
        for name in expected_names:
            assert any(name == rn for rn in result_names), f"Expected {name} not found in {result_names}"
    else:
        assert len(results) == 0, f"Expected 0 results, got {result_names}"

def test_search_max_results_limit(stress_project):
    """Verify max_results correctly truncates the generator."""
    limit = 10
    results = list(search_generator(stress_project, "file", "smart", "", max_results=limit))
    assert len(results) == limit

def test_search_file_size_limit(mock_project):
    """Verify search skips files larger than limit (default 5MB or as specified)."""
    # Create a dummy large file
    large_file = mock_project / "too_big.txt"
    with open(large_file, "wb") as f:
        f.seek(6 * 1024 * 1024) # 6 MB
        f.write(b"0")
    
    results = list(search_generator(mock_project, "FIND_ME", "content", ""))
    # File is 6MB, so it should be skipped by the 5MB limit
    assert not any("too_big.txt" in r["path"] for r in results)
