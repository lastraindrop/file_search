import threading
import pytest
from file_cortex_core import DataManager
from file_cortex_core.search import SHARED_SEARCH_POOL

def test_datamanager_singleton_concurrency():
    """Stress test DataManager singleton across multiple threads."""
    instances = []
    def get_instance():
        instances.append(DataManager())
    
    threads = [threading.Thread(target=get_instance) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # All threads must get the exact same object reference
    first = instances[0]
    for i in instances:
        assert i is first
    assert hasattr(first, 'data')
    assert isinstance(first.data, dict)

def test_shared_search_pool_is_singleton():
    """Verify SHARED_SEARCH_POOL is a module-level singleton."""
    # We can't import SHARED_SEARCH_POOL twice to get different objects
    # but we can verify it's the one used in search_generator or check its workers
    from file_cortex_core.search import SHARED_SEARCH_POOL as pool
    import os
    assert pool is not None
    # Use internal member to verify worker count
    assert pool._max_workers == (os.cpu_count() or 4)
