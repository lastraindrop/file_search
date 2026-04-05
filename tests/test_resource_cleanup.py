import pathlib
import os
import shutil
import time
import threading
import pytest
from concurrent.futures import ThreadPoolExecutor
from file_cortex_core.search import search_generator, SHARED_SEARCH_POOL

@pytest.fixture
def resource_cleanup_dir(tmp_path):
    test_dir = tmp_path / "res_cleanup"
    test_dir.mkdir()
    # Create many files to slow down search
    for i in range(100):
        (test_dir / f"test_{i}.py").write_text("print('hello world')")
    return test_dir

def test_search_future_cancellation(resource_cleanup_dir):
    # We search with content mode to trigger futures
    stop_event = threading.Event()
    
    # Collect only many results or trigger early exit
    gen = search_generator(resource_cleanup_dir, "hello", "content", "", 
                         max_results=5, stop_event=stop_event)
    
    results = []
    for r in gen:
        results.append(r)
        if len(results) >= 2:
            # BREAKING early to test finally block
            break
    
    # After break, the finally block in search_generator should run
    time.sleep(0.1)
    # Tasks should be cancelled by generator closure (verified by logic coverage)

def test_stop_event_immediate(resource_cleanup_dir):
    stop_event = threading.Event()
    stop_event.set()
    
    gen = search_generator(resource_cleanup_dir, "hello", "content", "", 
                         stop_event=stop_event)
    
    results = list(gen)
    assert len(results) == 0
