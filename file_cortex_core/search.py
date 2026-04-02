import pathlib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

SHARED_SEARCH_POOL = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

from .config import logger
from .utils import FileUtils, FormatUtils

def search_generator(root_dir, search_text, search_mode, manual_excludes, 
                     include_dirs=False, use_gitignore=True, 
                     is_inverse=False, case_sensitive=False, max_results=5000,
                     max_size_mb=5, stop_event=None,
                     positive_tags=None, negative_tags=None):
    """
    Multi-mode file search generator.
    """
    root_dir = pathlib.Path(root_dir)
    excludes = [e.lower().strip() for e in manual_excludes.split() if e.strip()]
    git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None
    
    count = 0
    search_text_processed = search_text.strip() if case_sensitive else search_text.lower().strip()
    # Merge raw search_text (split into keywords) and positive_tags
    all_pos = positive_tags.copy() if positive_tags else []
    if search_text_processed and search_text_processed not in ('.', '..'):
        for kw in search_text_processed.split():
            if kw not in all_pos:
                all_pos.append(kw)
    
    all_neg = negative_tags or []
    neg_keywords = [k if case_sensitive else k.lower() for k in all_neg]
    
    plain_pos = []
    regex_pos = []
    flags = 0 if case_sensitive else re.IGNORECASE
    for tag in all_pos:
        # Check if it's a sub-regex tag like /pattern/
        if tag.startswith('/') and tag.endswith('/') and len(tag) > 2:
            try:
                regex_pos.append(re.compile(tag[1:-1], flags))
                continue
            except re.error: pass
        
        plain_pos.append(tag if case_sensitive else tag.lower())
    
    re_obj = None
    if search_mode == 'regex' and search_text.strip():
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            re_obj = re.compile(search_text, flags)
        except re.error:
            return 

    def match_name(name, rel_path=None):
        # Allow empty search_text if tags are present
        # CR-05 Fix: Restore empty query check while allowing tags to proceed
        if not (search_text_processed or plain_pos or regex_pos or all_neg):
            found = False
        elif search_text_processed in ('.', '..') and not (plain_pos or regex_pos or all_neg):
            found = False
        else:
            target_name = name if case_sensitive else name.lower()
            target_path = str(rel_path).replace("\\", "/") if rel_path else target_name
            if not case_sensitive: target_path = target_path.lower()
            
            found = False
            if search_mode == 'smart':
                # Path matching: all positive keywords AND all regex tags AND no negative tags
                has_plain = all(k in target_path for k in plain_pos)
                has_regex = all(r.search(target_path) for r in regex_pos)
                has_neg = any(nk in target_path for nk in neg_keywords)
                found = has_plain and has_regex and not has_neg
            elif search_mode == 'exact':
                # Similar logic for exact: check full match on all plain_pos?
                # Usually exact means "this substring must be present". If multiple, all must be present.
                has_plain = all(k in target_path for k in plain_pos)
                has_regex = all(r.search(target_path) for r in regex_pos)
                has_neg = any(nk in target_path for nk in neg_keywords)
                found = has_plain and has_regex and not has_neg
            elif search_mode == 'regex' and re_obj:
                found = re_obj.search(name) is not None
            
        return found != is_inverse
    
    def match_content(path):
        if search_mode not in ('content', 'regex') or not search_text_processed:
            return False
        try:
            limit = max_size_mb * 1024 * 1024
            if path.stat().st_size > limit:
                return False
            # CR-13 Fix: Use read_text_smart for consistent encoding handling and OOM safety
            content = FileUtils.read_text_smart(path)
            found = False
            for line in content.splitlines():
                if search_mode == 'regex' and re_obj:
                    if re_obj.search(line):
                        found = True
                        break
                elif search_mode == 'content':
                    if search_text_processed in (line if case_sensitive else line.lower()):
                        found = True
                        break
            
            return found != is_inverse
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return False

    executor = SHARED_SEARCH_POOL
    content_futures = {}

    try:
        for root, dirs, files in os.walk(root_dir):
            rel_root = pathlib.Path(root).relative_to(root_dir)
            dirs[:] = [d for d in dirs if not FileUtils.should_ignore(d, rel_root / d, excludes, git_spec, is_dir=True)]
            
            if include_dirs:
                for d in dirs:
                    if match_name(d, rel_root / d):
                        full_d = pathlib.Path(root) / d
                        meta = FileUtils.get_metadata(full_d)
                        yield {
                            "path": str(full_d),
                            "match_type": "📁 Folder",
                            "mtime_fmt": FormatUtils.format_datetime(meta["mtime"]),
                            **meta
                        }

            for file in files:
                full_path = pathlib.Path(root) / file
                rel_path = rel_root / file
                if FileUtils.should_ignore(file, rel_path, excludes, git_spec, is_dir=False):
                    continue
                try:
                    meta = FileUtils.get_metadata(full_path)
                except Exception as e:
                    logger.error(f"Error getting metadata for {full_path}: {e}")
                    continue
                
                # Logic branching by mode
                if search_mode in ('smart', 'exact', 'regex'):
                    # Filename-centric modes
                    if match_name(file, rel_path):
                        count += 1
                        yield {
                            "path": str(full_path),
                            "match_type": "Inverse Match" if is_inverse else "Match",
                            "mtime_fmt": FormatUtils.format_datetime(meta["mtime"]),
                            **meta
                        }
                        if count >= max_results:
                            break
                    continue # Skip content check for path-focused modes
                
                # CR-02 Fix: Only run content search for 'content' mode. 
                # 'regex' mode handles filename matches at L145 and we should not double-count.
                if search_mode == 'content' and search_text:
                    if stop_event and stop_event.is_set():
                        break
                    
                    future = executor.submit(match_content, full_path)
                    content_futures[future] = {
                        "path": str(full_path),
                        "is_inverse": is_inverse,
                        **meta
                    }
                    if len(content_futures) >= 40:
                        # Adaptive Batching
                        batch = [f for f in content_futures if f.done()]
                        if not batch:
                            try:
                                next(as_completed(content_futures, timeout=0.01))
                                batch = [f for f in content_futures if f.done()]
                            except: pass
                        for f in batch:
                            try:
                                is_match = f.result()
                                info = content_futures.pop(f)
                                if is_match:
                                    count += 1
                                    yield {
                                        "path": info["path"],
                                        "match_type": "Inverse Content" if info["is_inverse"] else "Content Match",
                                        "mtime_fmt": FormatUtils.format_datetime(info["mtime"]),
                                        "size": info["size"],
                                        "mtime": info["mtime"],
                                        "ext": info["ext"]
                                    }
                                    if count >= max_results:
                                        break
                            except Exception:
                                if f in content_futures:
                                    content_futures.pop(f)
                        if count >= max_results:
                            break
                if count >= max_results or (stop_event and stop_event.is_set()): 
                    break
            if count >= max_results or (stop_event and stop_event.is_set()): 
                # Use a custom flag or modify dirs to stop os.walk
                dirs[:] = [] 
                break

        # Process remaining
        for f in as_completed(content_futures):
            if count >= max_results:
                break
            try:
                is_match = f.result()
                info = content_futures.pop(f)
                if is_match:
                    count += 1
                    yield {
                        "path": info["path"],
                        "match_type": "Inverse Content" if info["is_inverse"] else "Content Match",
                        "mtime_fmt": FormatUtils.format_datetime(info["mtime"]),
                        "size": info["size"],
                        "mtime": info["mtime"],
                        "ext": info["ext"]
                    }
            except Exception:
                pass
    finally:
        # Shutdown search quickly if generator is closed
        for f in content_futures:
            if not f.done():
                f.cancel()
        content_futures.clear()

class SearchWorker(threading.Thread):
    def __init__(self, root_dir, search_text, search_mode, manual_excludes, 
                 include_dirs, result_queue, stop_event, use_gitignore=True,
                 is_inverse=False, case_sensitive=False, max_results=5000,
                 max_size_mb=5, positive_tags=None, negative_tags=None):
        super().__init__()
        self.root_dir = root_dir
        self.search_text = search_text
        self.search_mode = search_mode
        self.manual_excludes = manual_excludes
        self.include_dirs = include_dirs
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.use_gitignore = use_gitignore
        self.is_inverse = is_inverse
        self.case_sensitive = case_sensitive
        self.max_results = max_results
        self.max_size_mb = max_size_mb
        self.positive_tags = positive_tags
        self.negative_tags = negative_tags
        self.daemon = True

    def run(self):
        gen = search_generator(self.root_dir, self.search_text, self.search_mode, 
                               self.manual_excludes, self.include_dirs, self.use_gitignore,
                                 self.is_inverse, self.case_sensitive, self.max_results,
                                 max_size_mb=self.max_size_mb, stop_event=self.stop_event,
                                 positive_tags=self.positive_tags, negative_tags=self.negative_tags)
        if gen is None:
            self.result_queue.put(("DONE", "DONE"))
            return
        for result in gen:
            if self.stop_event.is_set(): break
            self.result_queue.put(result)
        self.result_queue.put(("DONE", "DONE"))
