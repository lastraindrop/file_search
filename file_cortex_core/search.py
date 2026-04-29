#!/usr/bin/env python3
"""Search module for FileCortex.

Provides multi-mode file search with background threading support.
"""

import atexit
import os
import pathlib
import queue
import re
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Final

from pydantic import BaseModel, Field

from .config import logger
from .file_io import FileUtils

# Constants
MAX_SEARCH_RESULTS: Final = 5000
DEFAULT_BATCH_SIZE: Final = 40
DEFAULT_MAX_SIZE_MB: Final = 5

# Shared resource for parallel content search
SHARED_SEARCH_POOL: Final = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
atexit.register(SHARED_SEARCH_POOL.shutdown, wait=False)


class SearchQuery(BaseModel):
    """Container for search parameters."""
    text: str = ""
    mode: str = "smart"  # smart, exact, regex, content
    manual_excludes: str = ""
    include_dirs: bool = False
    use_gitignore: bool = True
    is_inverse: bool = False
    case_sensitive: bool = False
    max_results: int = MAX_SEARCH_RESULTS
    max_size_mb: int = DEFAULT_MAX_SIZE_MB
    positive_tags: list[str] = Field(default_factory=list)
    negative_tags: list[str] = Field(default_factory=list)


class PathMatcher:
    """Handles filename and path-based matching logic."""

    def __init__(self, query: SearchQuery):
        self.q = query
        self.flags = 0 if query.case_sensitive else re.IGNORECASE
        
        # Pre-process keywords
        processed_text = query.text.strip() if query.case_sensitive else query.text.lower().strip()
        self.all_pos = query.positive_tags.copy()
        if processed_text and processed_text not in (".", ".."):
            for kw in processed_text.split():
                if kw not in self.all_pos:
                    self.all_pos.append(kw)

        self.neg_keywords = [k if query.case_sensitive else k.lower() for k in query.negative_tags]
        
        self.plain_pos: list[str] = []
        self.regex_pos: list[re.Pattern] = []
        
        for tag in self.all_pos:
            if tag.startswith("/") and tag.endswith("/") and len(tag) > 2:
                try:
                    self.regex_pos.append(re.compile(tag[1:-1], self.flags))
                    continue
                except re.error:
                    pass
            self.plain_pos.append(tag if query.case_sensitive else tag.lower())

        self.main_re: re.Pattern | None = None
        if query.mode == "regex" and query.text.strip():
            try:
                self.main_re = re.compile(query.text, self.flags)
            except re.error:
                logger.warning(f"Invalid regex search pattern: {query.text}")

    def matches(self, name: str, rel_path: pathlib.Path | None = None) -> bool:
        """Determines if a name/path matches the criteria."""
        if not (self.q.text or self.all_pos or self.neg_keywords):
            found = False
        elif self.q.text.strip() in (".", "..") and not (self.all_pos or self.neg_keywords):
            found = False
        else:
            target_path = str(rel_path).replace("\\", "/") if rel_path else name
            if not self.q.case_sensitive:
                target_path = target_path.lower()

            found = False
            if self.q.mode == "smart":
                has_plain = all(k in target_path for k in self.plain_pos)
                has_regex = all(r.search(target_path) for r in self.regex_pos)
                has_neg = any(nk in target_path for nk in self.neg_keywords)
                found = has_plain and has_regex and not has_neg
            elif self.q.mode == "exact":
                target_text = self.q.text if self.q.case_sensitive else self.q.text.lower()
                found = (target_text in target_path) if target_text else True
                if found:
                    has_regex = all(r.search(target_path) for r in self.regex_pos)
                    has_neg = any(nk in target_path for nk in self.neg_keywords)
                    found = found and has_regex and not has_neg
            elif self.q.mode == "regex":
                if self.main_re:
                    found = self.main_re.search(target_path) is not None
                else:
                    # Fallback to tag matching if regex is invalid or empty
                    has_plain = all(k in target_path for k in self.plain_pos)
                    has_regex = all(r.search(target_path) for r in self.regex_pos)
                    has_neg = any(nk in target_path for nk in self.neg_keywords)
                    found = has_plain and has_regex and not has_neg

        return found != self.q.is_inverse


class ContentMatcher:
    """Handles file content-based matching logic."""

    def __init__(self, query: SearchQuery, path_matcher: PathMatcher):
        self.q = query
        self.pm = path_matcher

    def match_file(self, path: pathlib.Path) -> tuple[bool, str]:
        """Scans file content for matches."""
        if self.q.mode not in ("content", "regex") or not self.q.text.strip():
            return False, ""
        
        try:
            limit = self.q.max_size_mb * 1024 * 1024
            if path.stat().st_size > limit:
                return False, ""
            
            content = FileUtils.read_text_smart(path, max_bytes=limit)
            found = False
            snippet = ""
            
            target_query = self.q.text if self.q.case_sensitive else self.q.text.lower()
            
            for line in content.splitlines():
                target_line = line if self.q.case_sensitive else line.lower()
                
                if self.q.mode == "regex" and self.pm.main_re:
                    if self.pm.main_re.search(line):
                        found = True
                        snippet = line.strip()
                        break
                elif self.q.mode == "content":
                    if target_query in target_line:
                        found = True
                        snippet = line.strip()
                        break

            return (found != self.q.is_inverse), snippet
        except Exception as e:
            logger.error(f"Content search error in {path}: {e}")
            return False, ""


def search_generator(
    root_dir: pathlib.Path,
    search_text: str,
    search_mode: str,
    manual_excludes: str,
    include_dirs: bool = False,
    use_gitignore: bool = True,
    is_inverse: bool = False,
    case_sensitive: bool = False,
    max_results: int = MAX_SEARCH_RESULTS,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
    stop_event: threading.Event | None = None,
    positive_tags: list[str] | None = None,
    negative_tags: list[str] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Orchestrates the multi-mode search process.

    Args:
        root_dir: Directory to search.
        search_text: Query string.
        search_mode: Type of search.
        manual_excludes: Glob patterns to skip.
        include_dirs: Whether to return directory matches.
        use_gitignore: Respect .gitignore files.
        is_inverse: Flip match results.
        case_sensitive: Case sensitivity flag.
        max_results: Cap on result count.
        max_size_mb: Memory limit for content search.
        stop_event: External cancellation signal.
        positive_tags: List of required tags.
        negative_tags: List of forbidden tags.

    Yields:
        Metadata dictionaries for each match.
    """
    query = SearchQuery(
        text=search_text,
        mode=search_mode,
        manual_excludes=manual_excludes,
        include_dirs=include_dirs,
        use_gitignore=use_gitignore,
        is_inverse=is_inverse,
        case_sensitive=case_sensitive,
        max_results=max_results,
        max_size_mb=max_size_mb,
        positive_tags=positive_tags or [],
        negative_tags=negative_tags or [],
    )
    
    root_path = pathlib.Path(root_dir)
    excludes = [e.lower().strip() for e in query.manual_excludes.split() if e.strip()]
    git_spec = FileUtils.get_gitignore_spec(root_path) if query.use_gitignore else None
    
    path_matcher = PathMatcher(query)
    content_matcher = ContentMatcher(query, path_matcher)
    
    count = 0
    content_futures: dict[Any, dict[str, Any]] = {}

    try:
        for root, dirs, files in os.walk(root_path):
            if stop_event and stop_event.is_set():
                break

            rel_root = pathlib.Path(root).relative_to(root_path)
            
            # Prune directories based on ignore rules
            dirs[:] = [
                d for d in dirs 
                if not FileUtils.should_ignore(d, rel_root / d, excludes, git_spec, True)
            ]

            if query.include_dirs:
                for d in dirs:
                    if path_matcher.matches(d, rel_root / d):
                        count += 1
                        meta = FileUtils.get_metadata(pathlib.Path(root) / d)
                        yield {"match_type": "📁 Folder", **meta}
                        if count >= query.max_results:
                            dirs[:] = []
                            break

            for file in files:
                if stop_event and stop_event.is_set():
                    break
                    
                full_path = pathlib.Path(root) / file
                rel_path = rel_root / file
                
                if FileUtils.should_ignore(file, rel_path, excludes, git_spec, False):
                    continue
                
                try:
                    meta = FileUtils.get_metadata(full_path)
                except Exception:
                    continue

                # Mode Logic
                if query.mode in ("smart", "exact", "regex"):
                    if path_matcher.matches(file, rel_path):
                        count += 1
                        yield {
                            "match_type": "Inverse Match" if query.is_inverse else "Match",
                            **meta,
                        }
                    if count >= query.max_results:
                        break
                elif query.mode == "content" and query.text:
                    future = SHARED_SEARCH_POOL.submit(content_matcher.match_file, full_path)
                    content_futures[future] = meta
                    
                    if len(content_futures) >= DEFAULT_BATCH_SIZE:
                        # Process done futures to maintain result order and flow
                        done_batch = [f for f in content_futures if f.done()]
                        if not done_batch:
                            try:
                                next(as_completed(content_futures, timeout=0.01))
                                done_batch = [f for f in content_futures if f.done()]
                            except Exception:
                                pass
                                
                        for f in done_batch:
                            is_match, snippet = f.result()
                            info = content_futures.pop(f)
                            if is_match:
                                count += 1
                                yield {
                                    "match_type": "Content Match",
                                    "snippet": snippet,
                                    **info,
                                }
                                if count >= query.max_results:
                                    break
                    if count >= query.max_results:
                        break

            if count >= query.max_results:
                dirs[:] = []
                break

        # Final cleanup of remaining content futures
        for f in as_completed(content_futures):
            if count >= query.max_results:
                break
            try:
                is_match, snippet = f.result()
                info = content_futures.pop(f)
                if is_match:
                    count += 1
                    yield {
                        "match_type": "Content Match",
                        "snippet": snippet,
                        **info,
                    }
            except Exception:
                pass

    finally:
        # Cancel any pending content search tasks
        for f in content_futures:
            if not f.done():
                f.cancel()
        content_futures.clear()


class SearchWorker(threading.Thread):
    """Background search runner for UI integration."""

    def __init__(
        self,
        root_dir: pathlib.Path,
        search_text: str,
        search_mode: str,
        manual_excludes: str,
        include_dirs: bool,
        result_queue: queue.Queue,
        stop_event: threading.Event,
        use_gitignore: bool = True,
        is_inverse: bool = False,
        case_sensitive: bool = False,
        max_results: int = MAX_SEARCH_RESULTS,
        max_size_mb: int = DEFAULT_MAX_SIZE_MB,
        positive_tags: list[str] | None = None,
        negative_tags: list[str] | None = None,
    ) -> None:
        """Initializes the background worker."""
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

    def run(self) -> None:
        """Executes the search and feeds the result queue."""
        gen = search_generator(
            self.root_dir,
            self.search_text,
            self.search_mode,
            self.manual_excludes,
            self.include_dirs,
            self.use_gitignore,
            self.is_inverse,
            self.case_sensitive,
            self.max_results,
            max_size_mb=self.max_size_mb,
            stop_event=self.stop_event,
            positive_tags=self.positive_tags,
            negative_tags=self.negative_tags,
        )
        try:
            for result in gen:
                if self.stop_event.is_set():
                    break
                self.result_queue.put(result)
        finally:
            gen.close()
        self.result_queue.put(("DONE", "DONE"))
