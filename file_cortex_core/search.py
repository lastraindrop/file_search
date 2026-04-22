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
from typing import Any

from .config import logger
from .file_io import FileUtils

MAX_SEARCH_RESULTS = 5000
DEFAULT_BATCH_SIZE = 40
DEFAULT_MAX_SIZE_MB = 5

SHARED_SEARCH_POOL = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
atexit.register(SHARED_SEARCH_POOL.shutdown, wait=False)


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
    """Multi-mode file search generator.

    Args:
        root_dir: Root directory to search.
        search_text: Search query text.
        search_mode: Mode ('smart', 'exact', 'regex', 'content').
        manual_excludes: Space-separated exclusion patterns.
        include_dirs: Whether to include directories in results.
        use_gitignore: Whether to respect .gitignore.
        is_inverse: Return non-matching files.
        case_sensitive: Case-sensitive search.
        max_results: Maximum results to return.
        max_size_mb: Max file size for content search.
        stop_event: Event to signal cancellation.
        positive_tags: Additional positive match tags.
        negative_tags: Additional negative match tags.

    Yields:
        Dictionary with match information.
    """
    root_dir = pathlib.Path(root_dir)
    excludes = [e.lower().strip() for e in manual_excludes.split() if e.strip()]
    git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None

    count = 0
    search_text_processed = (
        search_text.strip() if case_sensitive else search_text.lower().strip()
    )
    all_pos = positive_tags.copy() if positive_tags else []
    if search_text_processed and search_text_processed not in (".", ".."):
        for kw in search_text_processed.split():
            if kw not in all_pos:
                all_pos.append(kw)

    all_neg = negative_tags or []
    neg_keywords = [k if case_sensitive else k.lower() for k in all_neg]

    plain_pos: list[str] = []
    regex_pos: list[re.Pattern] = []
    flags = 0 if case_sensitive else re.IGNORECASE
    for tag in all_pos:
        try:
            if tag.startswith("/") and tag.endswith("/") and len(tag) > 2:
                try:
                    regex_pos.append(re.compile(tag[1:-1], flags))
                    continue
                except re.error:
                    pass

            plain_pos.append(tag if case_sensitive else tag.lower())
        except Exception:
            pass

    re_obj: re.Pattern | None = None
    if search_mode == "regex" and search_text.strip():
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            re_obj = re.compile(search_text, flags)
        except re.error:
            return

    def match_name(name: str, rel_path: pathlib.Path | None = None) -> bool:
        """Checks if a name matches the search criteria.

        Args:
            name: File/directory name.
            rel_path: Relative path.

        Returns:
            True if matches.
        """
        if not (search_text_processed or plain_pos or regex_pos or all_neg):
            found = False
        elif search_text_processed in (".", "..") and not (
            plain_pos or regex_pos or all_neg
        ):
            found = False
        else:
            target_name = name if case_sensitive else name.lower()
            target_path = str(rel_path).replace("\\", "/") if rel_path else target_name
            if not case_sensitive:
                target_path = target_path.lower()

            found = False
            if search_mode == "smart":
                has_plain = all(k in target_path for k in plain_pos)
                has_regex = all(r.search(target_path) for r in regex_pos)
                has_neg = any(nk in target_path for nk in neg_keywords)
                found = has_plain and has_regex and not has_neg
            elif search_mode == "exact":
                if search_text_processed:
                    found = search_text_processed in target_path
                else:
                    found = all(k in target_path for k in plain_pos)

                if found:
                    has_regex = all(r.search(target_path) for r in regex_pos)
                    has_neg = any(nk in target_path for nk in neg_keywords)
                    found = found and has_regex and not has_neg
            elif search_mode == "regex":
                if re_obj:
                    found = re_obj.search(target_path) is not None
                else:
                    if plain_pos or regex_pos:
                        has_plain = all(k in target_path for k in plain_pos)
                        has_regex = all(r.search(target_path) for r in regex_pos)
                        has_neg = any(nk in target_path for nk in neg_keywords)
                        found = has_plain and has_regex and not has_neg
                    else:
                        found = False

        return found != is_inverse

    def match_content(
        path: pathlib.Path,
    ) -> tuple[bool, str]:
        """Checks if file content matches search criteria.

        Args:
            path: File path to check.

        Returns:
            Tuple of (is_match, snippet).
        """
        if search_mode not in ("content", "regex") or not search_text_processed:
            return False, ""
        try:
            limit = max_size_mb * 1024 * 1024
            if path.stat().st_size > limit:
                return False, ""
            content = FileUtils.read_text_smart(path)
            found = False
            snippet = ""
            for line in content.splitlines():
                target_line = line if case_sensitive else line.lower()
                if search_mode == "regex" and re_obj:
                    if re_obj.search(line):
                        found = True
                        snippet = line.strip()
                        break
                elif search_mode == "content":
                    if search_text_processed in target_line:
                        found = True
                        snippet = line.strip()
                        break

            return (found != is_inverse), snippet
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return False, ""

    executor = SHARED_SEARCH_POOL
    content_futures: dict[Any, dict[str, Any]] = {}

    try:
        for root, dirs, files in os.walk(root_dir):
            rel_root = pathlib.Path(root).relative_to(root_dir)
            dirs[:] = [
                d
                for d in dirs
                if not FileUtils.should_ignore(
                    d, rel_root / d, excludes, git_spec, True
                )
            ]

            if include_dirs:
                for d in dirs:
                    if match_name(d, rel_root / d):
                        count += 1
                        full_d = pathlib.Path(root) / d
                        meta = FileUtils.get_metadata(full_d)
                        yield {"match_type": "📁 Folder", **meta}
                        if count >= max_results:
                            dirs[:] = []
                            break

            for file in files:
                full_path = pathlib.Path(root) / file
                rel_path = rel_root / file
                if FileUtils.should_ignore(file, rel_path, excludes, git_spec, False):
                    continue
                try:
                    meta = FileUtils.get_metadata(full_path)
                except Exception as e:
                    logger.error(f"Error getting metadata for {full_path}: {e}")
                    continue

                if search_mode in ("smart", "exact", "regex"):
                    if match_name(file, rel_path):
                        count += 1
                        yield {
                            "match_type": "Inverse Match" if is_inverse else "Match",
                            **meta,
                        }
                        if count >= max_results:
                            break
                    continue

                if search_mode == "content" and search_text:
                    if stop_event and stop_event.is_set():
                        break

                    future = executor.submit(match_content, full_path)
                    content_futures[future] = {
                        "path": str(full_path),
                        "is_inverse": is_inverse,
                        **meta,
                    }
                    if len(content_futures) >= DEFAULT_BATCH_SIZE:
                        batch = [f for f in content_futures if f.done()]
                        if not batch:
                            try:
                                next(as_completed(content_futures, timeout=0.01))
                                batch = [f for f in content_futures if f.done()]
                            except Exception:
                                pass
                        for f in batch:
                            try:
                                is_match, snippet = f.result()
                                info = content_futures.pop(f)
                                if is_match:
                                    count += 1
                                    yield {
                                        "match_type": (
                                            "Inverse Content"
                                            if info["is_inverse"]
                                            else "Content Match"
                                        ),
                                        "snippet": snippet,
                                        **info,
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
                dirs[:] = []
                break

        for f in as_completed(content_futures):
            if count >= max_results:
                break
            try:
                is_match, snippet = f.result()
                info = content_futures.pop(f)
                if is_match:
                    count += 1
                    yield {
                        "match_type": (
                            "Inverse Content" if info["is_inverse"] else "Content Match"
                        ),
                        "snippet": snippet,
                        **info,
                    }
            except Exception:
                pass
    finally:
        for f in content_futures:
            if not f.done():
                f.cancel()
        content_futures.clear()


class SearchWorker(threading.Thread):
    """Background thread worker for file search."""

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
        """Initializes the search worker.

        Args:
            root_dir: Root directory to search.
            search_text: Search query.
            search_mode: Search mode.
            manual_excludes: Exclusion patterns.
            include_dirs: Include directories in results.
            result_queue: Queue for results.
            stop_event: Event for cancellation.
            use_gitignore: Respect .gitignore.
            is_inverse: Inverse search.
            case_sensitive: Case-sensitive search.
            max_results: Maximum results.
            max_size_mb: Max file size for content search.
            positive_tags: Positive match tags.
            negative_tags: Negative match tags.
        """
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
        """Main worker loop."""
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
