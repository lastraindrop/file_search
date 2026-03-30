import pytest
import pathlib
import queue
import threading
import time
import os
from file_cortex_core import DuplicateWorker

def test_duplicate_finder_basic(mock_project):
    """Verify that DuplicateWorker correctly identifies identical files by hash."""
    root = mock_project
    # 1. Create identical pair
    f1 = root / "dup1.txt"
    f2 = root / "dup2.txt"
    content = "this is a duplicate"
    f1.write_text(content)
    f2.write_text(content)
    
    # 2. Create unique file
    f3 = root / "unique.txt"
    f3.write_text("this is unique content")
    
    # 3. Create same size, different content
    f4 = root / "size_match_1.txt"
    f5 = root / "size_match_2.txt"
    f4.write_text("ABC")
    f5.write_text("XYZ")
    
    res_queue = queue.Queue()
    stop_event = threading.Event()
    
    worker = DuplicateWorker(str(root), "", True, res_queue, stop_event)
    worker.start()
    
    results = []
    # Poll for results with timeout
    start_time = time.time()
    while time.time() - start_time < 5:
        try:
            res = res_queue.get(timeout=0.1)
            if res == ("DONE", True):
                break
            results.append(res)
        except queue.Empty:
            continue
            
    # Should only find f1 and f2 as duplicates
    assert len(results) == 1
    assert results[0]["size"] == len(content)
    # Norm paths for comparison
    found_paths = [os.path.normpath(p) for p in results[0]["paths"]]
    expected_paths = [os.path.normpath(str(f1)), os.path.normpath(str(f2))]
    assert set(found_paths) == set(expected_paths)

def test_duplicate_finder_stop_event(mock_project):
    """Verify that DuplicateWorker respects the stop event."""
    root = mock_project
    # Create many files
    for i in range(50):
        (root / f"file_{i}.txt").write_text("constant content")
        
    res_queue = queue.Queue()
    stop_event = threading.Event()
    
    worker = DuplicateWorker(str(root), "", True, res_queue, stop_event)
    worker.start()
    
    # Stop immediately
    stop_event.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
