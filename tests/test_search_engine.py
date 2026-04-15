import pytest
import pathlib
from file_cortex_core import search_generator, FileUtils

# -----------------------------------------------------------------------------
# 1. Search Mode Matrix
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("mode,query,expected_substring", [
    ("smart", "main", "main.py"),
    ("exact", "src/main.py", "main.py"),
    ("regex", "m.*\\.py$", "main.py"),
    ("content", "hello", "main.py") # main.py has 'print("hello")'
])
def test_search_modes_core(mock_project, mode, query, expected_substring):
    """Verify core search modes using search_generator."""
    results = list(search_generator(str(mock_project), query, mode, ""))
    assert len(results) >= 1
    paths = [r["path"].replace("\\", "/") for r in results]
    assert any(expected_substring in p for p in paths)

# -----------------------------------------------------------------------------
# 2. Parameter Permutations
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("case_sensitive,is_inverse,use_gitignore", [
    (True, False, True),
    (False, True, False),
    (False, False, True)
])
def test_search_parameters_matrix(mock_project, case_sensitive, is_inverse, use_gitignore):
    """Integrate permutations: Case, Inverse, and Gitignore compliance."""
    # query that matches main.py
    query = "MAIN" if not case_sensitive else "main"
    results = list(search_generator(
        str(mock_project), query, "smart", "", 
        case_sensitive=case_sensitive, is_inverse=is_inverse, use_gitignore=use_gitignore
    ))
    
    has_main = any("main.py" in r["path"] for r in results)
    
    if is_inverse:
        assert not has_main
    else:
        # Case check
        if case_sensitive and query == "MAIN":
            assert not has_main
        else:
            assert has_main

def test_search_gitignore_compliance(mock_project):
    """Verify that ignored files are indeed ignored unless use_gitignore=False."""
    # error.log is in .gitignore
    ignored_q = "error.log"
    
    # 1. Normal (Ignored)
    res_normal = list(search_generator(str(mock_project), ignored_q, "smart", "", use_gitignore=True))
    assert not any("error.log" in r["path"] for r in res_normal)
    
    # 2. Override (Found)
    res_override = list(search_generator(str(mock_project), ignored_q, "smart", "", use_gitignore=False))
    assert any("error.log" in r["path"] for r in res_override)

# -----------------------------------------------------------------------------
# 3. Tag Search Logic
# -----------------------------------------------------------------------------

def test_search_tags_complex(mock_project):
    """Verify positive, negative, and regex-style tags."""
    # Find all .py files but NOT those containing 'main'
    results = list(search_generator(
        str(mock_project), 
        search_text="", 
        search_mode="smart", 
        manual_excludes="",
        positive_tags=["/.py$/"], # Regex tag
        negative_tags=["main"]
    ))
    
    paths = [r["path"] for r in results]
    # Should have other .py if any, but NOT main.py
    assert not any("main.py" in p for p in paths)

# -----------------------------------------------------------------------------
# 4. Resource & Perf Controls
# -----------------------------------------------------------------------------

def test_search_limits_and_stop_event(stress_project):
    """Verify max_results and stop_event interruption."""
    import threading
    stop_event = threading.Event()
    
    # 1. Max Results
    results = list(search_generator(str(stress_project), "file", "smart", "", max_results=50))
    assert len(results) == 50
    
    # 2. Early Stop
    stop_event.set()
    results_stopped = list(search_generator(str(stress_project), "file", "smart", "", stop_event=stop_event))
    assert len(results_stopped) < 10 # Should bail out very quickly
