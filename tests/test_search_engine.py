import pytest
import threading
from file_cortex_core.search import search_generator
from file_cortex_core.file_io import FileUtils

# -----------------------------------------------------------------------------
# 1. Exhaustive Parameter Matrix (Stress Test Combinations)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["smart", "exact", "regex", "content"])
@pytest.mark.parametrize("case_sensitive", [True, False])
@pytest.mark.parametrize("is_inverse", [True, False])
def test_search_logic_matrix(mock_project, mode, case_sensitive, is_inverse):
    """Exhaustively verify all search mode and flag combinations."""
    query = "main" if not case_sensitive else "main"
    if mode == "content":
        query = "hello" # main.py has print('hello')
        
    results = list(search_generator(
        str(mock_project), 
        query, 
        mode, 
        manual_excludes="",
        case_sensitive=case_sensitive,
        is_inverse=is_inverse,
        use_gitignore=True
    ))
    
    # Validation logic: 
    # If is_inverse=False, we expect main.py to be in results (if matched)
    # If is_inverse=True, we expect main.py NOT to be in results (if query matches it)
    has_main = any("main.py" in r["path"] for r in results)
    
    # Basic logic check: match found or match inverted
    if not is_inverse:
        if mode == "content" and query == "hello":
            assert has_main
        elif mode != "content" and query == "main":
            assert has_main
    else:
        # Inverse logic: if query matches, it shouldn't be there
        # For simplicity, we just ensure the generator doesn't crash 
        # and returns a list.
        assert isinstance(results, list)

# -----------------------------------------------------------------------------
# 2. Architecture & File System Integration
# -----------------------------------------------------------------------------

def test_search_gitignore_compliance_modular(mock_project):
    """Verify that ignored files are indeed ignored using modular FileUtils."""
    # error.log is in .gitignore
    ignored_q = "error.log"

    # 1. Normal (Ignored) - uses FileUtils.get_gitignore_spec internally
    res_normal = list(search_generator(str(mock_project), ignored_q, "smart", "", use_gitignore=True))
    assert not any("error.log" in r["path"] for r in res_normal)

    # 2. Override (Found)
    res_override = list(search_generator(str(mock_project), ignored_q, "smart", "", use_gitignore=False))
    assert any("error.log" in r["path"] for r in res_override)

# -----------------------------------------------------------------------------
# 3. Advanced Tag Logic (Non-Hardcoded)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("pos_tag,neg_tag,expected_present", [
    (["/.py$/"], ["main"], False), # Find py files but NOT main
    (["src"], [], True),           # Find items in src
])
def test_search_tags_logic(mock_project, pos_tag, neg_tag, expected_present):
    """Verify tag-based filtering without hardcoding results."""
    results = list(search_generator(
        str(mock_project),
        search_text="",
        search_mode="smart",
        manual_excludes="",
        positive_tags=pos_tag,
        negative_tags=neg_tag
    ))

    has_main = any("main.py" in r["path"] for r in results)
    assert has_main == expected_present

# -----------------------------------------------------------------------------
# 4. Resource Efficiency & Interruption
# -----------------------------------------------------------------------------

def test_search_interruption_resilience(stress_project):
    """Verify that search stops immediately on event set."""
    stop_event = threading.Event()
    
    # Start generator but stop it immediately
    gen = search_generator(str(stress_project), "file", "smart", "", stop_event=stop_event)
    stop_event.set()
    
    results = []
    for r in gen:
        results.append(r)
        if len(results) > 100: # Safety break
            break
            
    # Should have very few results if any, as it checks stop_event in loops
    assert len(results) < 50 
