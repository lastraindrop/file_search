import hashlib
import os
import pathlib
import threading
import queue
from .utils import FileUtils, FormatUtils
from .config import logger

class DuplicateWorker(threading.Thread):
    """
    Background worker to find duplicate files based on size and SHA256 hash.
    Step 1: Group files by size (ignore singular sizes).
    Step 2: Calculate Hash for potential duplicates in chunks.
    """
    def __init__(self, root_dir, manual_excludes, use_gitignore, result_queue, stop_event):
        super().__init__()
        self.root_dir = pathlib.Path(root_dir)
        self.excludes = [e.lower().strip() for e in manual_excludes.split() if e.strip()]
        self.git_spec = FileUtils.get_gitignore_spec(self.root_dir) if use_gitignore else None
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.daemon = True # Ensure thread dies if app exits

    def _get_hash(self, file_path, chunk_size=1024*1024): # 1MB chunks for balanced disk I/O
        m = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while True:
                    if self.stop_event.is_set(): return None
                    data = f.read(chunk_size)
                    if not data:
                        break
                    m.update(data)
            return m.hexdigest()
        except Exception as e:
            logger.error(f"Hashing failed for {file_path}: {e}")
            return None

    def run(self):
        logger.info(f"AUDIT - Starting duplicate scan in {self.root_dir}")
        size_map = {} # {size: [path, ...]}
        try:
            # Phase 1: Fast Walk & Size Grouping
            for root, dirs, files in os.walk(self.root_dir):
                if self.stop_event.is_set(): return
                
                rel_root = pathlib.Path(root).relative_to(self.root_dir)
                # Apply ignore logic to dirs to prune early
                dirs[:] = [d for d in dirs if not FileUtils.should_ignore(d, rel_root / d, self.excludes, self.git_spec, is_dir=True)]
                
                for file in files:
                    full_p = pathlib.Path(root) / file
                    rel_p = rel_root / file
                    if FileUtils.should_ignore(file, rel_p, self.excludes, self.git_spec, is_dir=False):
                        continue
                    
                    try:
                        stat = full_p.stat()
                        sz = stat.st_size
                        if sz == 0: continue # Skip empty files 
                        if sz not in size_map:
                            size_map[sz] = []
                        size_map[sz].append(full_p)
                    except Exception:
                        continue

            # Phase 2: Hash Check for size collisions
            potential_groups = {s: p for s, p in size_map.items() if len(p) > 1}
            final_groups = {} # { (size, hash): [path, ...] }
            
            for size, paths in potential_groups.items():
                if self.stop_event.is_set(): return
                
                # Internal map for this size group
                hash_sub_map = {} # {hash: [path, ...]}
                for p in paths:
                    if self.stop_event.is_set(): return
                    h = self._get_hash(p)
                    if h:
                        if h not in hash_sub_map:
                            hash_sub_map[h] = []
                        hash_sub_map[h].append(p)
                
                # Check for actual duplicates in this size bucket
                for h, p_list in hash_sub_map.items():
                    if len(p_list) > 1:
                        self.result_queue.put({
                            "hash": h,
                            "size": size,
                            "paths": [str(x) for x in p_list]
                        })
            
            self.result_queue.put(("DONE", True))
            logger.info("AUDIT - Duplicate scan complete.")

        except Exception as e:
            logger.error(f"Duplicate scan failed: {e}")
            self.result_queue.put(("ERROR", str(e)))
