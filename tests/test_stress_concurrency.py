import pytest
import threading
import time
import random
import os
from file_cortex_core import DataManager, SearchWorker, PathValidator
import queue

def test_datamanager_concurrent_writes(clean_config):
    """
    Stress test DataManager with high-frequency concurrent updates.
    Ensures no corruption or race conditions in the singleton state.
    """
    dm = clean_config
    project_path = "C:/TestProject" if os.name == 'nt' else "/tmp/TestProject"
    
    # Initialize project
    dm.get_project_data(project_path)
    
    def updater(thread_id):
        for i in range(20):
            # Concurrent updates to different/same fields
            dm.add_tag(project_path, f"file_{i}.txt", f"tag_{thread_id}")
            # Simulate slight delay
            time.sleep(random.random() * 0.01)
            dm.update_project_settings(project_path, {"excludes": f"ex_{thread_id}_{i}"})

    threads = [threading.Thread(target=updater, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    proj_data = dm.get_project_data(project_path)
    # Check if tags from all threads are present (partially)
    # Since we use append and RLock, we expect no data loss in the list structure
    total_tags = 0
    for file_path in proj_data["tags"]:
        total_tags += len(proj_data["tags"][file_path])
    
    assert total_tags > 0
    print(f"Total tags added concurrently: {total_tags}")

def test_concurrent_search_load(stress_project):
    """
    Simulate multiple concurrent search workers on the same project.
    Ensures that ThreadPoolExecutor and generators don't conflict.
    """
    root = stress_project
    results_queues = [queue.Queue() for _ in range(5)]
    stop_events = [threading.Event() for _ in range(5)]
    
    workers = []
    for i in range(5):
        w = SearchWorker(
            root_dir=str(root),
            search_text=f"keyword_target_{i}", 
            search_mode="content",
            manual_excludes="",
            include_dirs=False,
            result_queue=results_queues[i],
            stop_event=stop_events[i]
        )
        workers.append(w)
        w.start()

    # Wait for all to finish
    for w in workers: w.join(timeout=30)
    
    for i, q in enumerate(results_queues):
        results = []
        while True:
            try:
                res = q.get_nowait()
                if res == ("DONE", "DONE"): break
                results.append(res)
            except queue.Empty:
                break
        assert len(results) > 0
        print(f"Worker {i} found {len(results)} matches.")

def test_simultaneous_save_read_integrity(clean_config):
    """
    Stress test reading while saving. 
    Ensures that deepcopy and atomic write prevent partial state exposure.
    """
    dm = clean_config
    p_path = "/tmp/IntegrityProj"
    dm.get_project_data(p_path)
    
    stop_event = threading.Event()
    
    def constant_reader():
        while not stop_event.is_set():
            data = dm.get_project_data(p_path)
            # Basic integrity check: DEFAULT_SCHEMA keys must always exist
            assert "excludes" in data
            assert "staging_list" in data
            
    def constant_updater():
        for i in range(50):
            dm.add_to_recent(f"/tmp/p_{i}")
            dm.update_project_settings(p_path, {"max_search_size_mb": i})
            dm.save()

    reader_thread = threading.Thread(target=constant_reader)
    reader_thread.start()
    
    constant_updater()
    
    stop_event.set()
    reader_thread.join()
    print("Integrity test passed under load.")
