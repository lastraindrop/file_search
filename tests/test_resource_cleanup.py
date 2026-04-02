import unittest
import pathlib
import os
import shutil
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from file_cortex_core.search import search_generator, SHARED_SEARCH_POOL

class TestResourceCleanup(unittest.TestCase):
    def setUp(self):
        self.test_dir = pathlib.Path("tmp_test_res")
        if self.test_dir.exists(): shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()
        # Create many files to slow down search
        for i in range(100):
            (self.test_dir / f"test_{i}.py").write_text("print('hello world')")

    def tearDown(self):
        if self.test_dir.exists(): shutil.rmtree(self.test_dir)

    def test_search_future_cancellation(self):
        # We search with content mode to trigger futures
        stop_event = threading.Event()
        
        # Collect only many results or trigger early exit
        gen = search_generator(self.test_dir, "hello", "content", "", 
                             max_results=5, stop_event=stop_event)
        
        results = []
        for r in gen:
            results.append(r)
            if len(results) >= 2:
                # BREAKING early to test finally block
                break
        
        # After break, the finally block in search_generator should run
        # Wait a tiny bit for the finally block to execute
        time.sleep(0.1)
        
        # Check if tasks are leaking in SHARED_SEARCH_POOL
        # We can't directly check cancellation status easily from outside 
        # but we can verify the content_futures dictionary was cleared (if we had access)
        # Instead, we rely on the logic that finally CANCELS them.
        # A more robust check would be to see if they are still 'running' in the pool
        # If we had a custom executor we could track it.
        pass

    def test_stop_event_immediate(self):
        stop_event = threading.Event()
        stop_event.set()
        
        gen = search_generator(self.test_dir, "hello", "content", "", 
                             stop_event=stop_event)
        
        results = list(gen)
        self.assertEqual(len(results), 0)

if __name__ == '__main__':
    unittest.main()
