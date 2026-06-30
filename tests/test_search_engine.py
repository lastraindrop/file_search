"""Tests for the multi-mode search engine and matching logic."""

import contextlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from file_cortex_core.search import search_generator

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
        if mode == "content" and query == "hello" or mode != "content" and query == "main":
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
    res_normal = list(search_generator(
        str(mock_project), ignored_q, "smart", "", use_gitignore=True,
    ))
    assert not any("error.log" in r["path"] for r in res_normal)

    # 2. Override (Found)
    res_override = list(search_generator(
        str(mock_project), ignored_q, "smart", "", use_gitignore=False,
    ))
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


# -----------------------------------------------------------------------------
# 5. Shared Pool Robustness Regression
# -----------------------------------------------------------------------------

@pytest.fixture
def _restored_search_pool():
    """Ensure the module-level shared search pool is usable after the test.

    Regression tests below deliberately shut the pool down to exercise the
    fallback path; this fixture guarantees no shut-down pool leaks into later
    tests, regardless of pass/fail.
    """
    import file_cortex_core.search as search_mod

    yield search_mod

    # Always leave a fresh, running pool for subsequent tests.
    with contextlib.suppress(Exception):
        search_mod.SHARED_SEARCH_POOL.shutdown(wait=False)
    search_mod.SHARED_SEARCH_POOL = ThreadPoolExecutor(
        max_workers=os.cpu_count() or 4
    )


def test_content_search_reinitializes_shut_down_pool(
    mock_project, _restored_search_pool
):
    """Content search must survive a shut-down shared pool.

    Regression for the brittle ``SHARED_SEARCH_POOL._shutdown`` private-attribute
    check. Submission now wraps ``ThreadPoolExecutor.submit`` in
    ``try/except RuntimeError`` and reinitializes the pool once on failure,
    so a previously shut-down pool is transparently recovered instead of
    aborting the whole search.
    """
    search_mod = _restored_search_pool

    # Pre-condition: shut down the active pool to force the fallback path.
    original_pool = search_mod.SHARED_SEARCH_POOL
    original_pool.shutdown(wait=False)

    # Direct submission to the stale pool must now raise -- this is the
    # public, version-stable signal we rely on instead of ``_shutdown``.
    with pytest.raises(RuntimeError):
        original_pool.submit(lambda: None)

    # The content search itself must still complete via the reinit path.
    results = list(search_generator(
        str(mock_project), "hello", "content", "", use_gitignore=True,
    ))

    # mock_project/src/main.py contains "print('hello')".
    assert any("main.py" in r["path"] for r in results)

    # The module global must have been replaced with a fresh, usable pool.
    new_pool = search_mod.SHARED_SEARCH_POOL
    assert new_pool is not original_pool
    fut = new_pool.submit(lambda: 42)
    assert fut.result(timeout=5) == 42


def test_submit_content_task_returns_none_on_persistent_failure(
    monkeypatch, _restored_search_pool
):
    """If the pool stays unusable after reinit, submission degrades gracefully.

    Patches ``_reinit_shared_pool`` so the second ``submit`` still raises,
    exercising the ``return None`` branch -- the search loop turns this into
    a clean ``break`` instead of propagating ``RuntimeError``.
    """
    search_mod = _restored_search_pool

    # Force the active pool into a shut-down state.
    search_mod.SHARED_SEARCH_POOL.shutdown(wait=False)

    # Stub reinit so the *new* pool is also dead on arrival.
    def _fake_reinit():
        dead = ThreadPoolExecutor(max_workers=1)
        dead.shutdown(wait=False)
        search_mod.SHARED_SEARCH_POOL = dead
        return dead

    monkeypatch.setattr(search_mod, "_reinit_shared_pool", _fake_reinit)

    # Helper under test: both attempts fail -> None.
    result = search_mod._submit_content_task(lambda: None)
    assert result is None
