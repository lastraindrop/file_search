#!/usr/bin/env python3
"""Duplicate file detection module.

Finds duplicate files based on size and SHA256 hash comparison.
"""

import hashlib
import os
import pathlib
import queue
import threading
from typing import Any

from .config import logger
from .utils import FileUtils


class DuplicateWorker(threading.Thread):
    """Background worker to find duplicate files based on size and SHA256 hash.

    The worker performs a two-phase approach:
    1. Group files by size (ignoring singular sizes).
    2. Calculate hashes for potential duplicates in chunks.
    """

    def __init__(
        self,
        root_dir: pathlib.Path,
        manual_excludes: str,
        use_gitignore: bool,
        result_queue: queue.Queue,
        stop_event: threading.Event,
    ) -> None:
        """Initializes the duplicate worker.

        Args:
            root_dir: The root directory to scan.
            manual_excludes: Space-separated exclusion patterns.
            use_gitignore: Whether to respect .gitignore files.
            result_queue: Queue for reporting results.
            stop_event: Event to signal cancellation.
        """
        super().__init__()
        self.root_dir = pathlib.Path(root_dir)
        self.excludes = [
            e.lower().strip() for e in manual_excludes.split() if e.strip()
        ]
        self.git_spec = (
            FileUtils.get_gitignore_spec(self.root_dir) if use_gitignore else None
        )
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.daemon = True

    def _get_hash(
        self, file_path: pathlib.Path, chunk_size: int = 1024 * 1024
    ) -> str | None:
        """Computes SHA256 hash of a file.

        Args:
            file_path: The file to hash.
            chunk_size: Size of chunks to read.

        Returns:
            Hex digest of the file or None on error.
        """
        m = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while True:
                    if self.stop_event.is_set():
                        return None
                    data = f.read(chunk_size)
                    if not data:
                        break
                    m.update(data)
            return m.hexdigest()
        except Exception as e:
            logger.error(f"Hashing failed for {file_path}: {e}")
            return None

    def run(self) -> None:
        """Main worker loop that scans for duplicates."""
        logger.info(f"AUDIT - Starting duplicate scan in {self.root_dir}")
        size_map: dict[int, list[pathlib.Path]] = {}

        try:
            for root, dirs, files in os.walk(self.root_dir):
                if self.stop_event.is_set():
                    return

                try:
                    rel_root = pathlib.Path(root).relative_to(self.root_dir)
                except (ValueError, RuntimeError):
                    norm_root = os.path.normcase(os.path.abspath(root))
                    norm_base = os.path.normcase(os.path.abspath(self.root_dir))
                    if norm_root.startswith(norm_base):
                        rel_root = pathlib.Path(
                            norm_root[len(norm_base) :].lstrip(os.sep)
                        )
                    else:
                        rel_root = pathlib.Path(os.path.basename(root))

                dirs[:] = [
                    d
                    for d in dirs
                    if not FileUtils.should_ignore(
                        d, rel_root / d, self.excludes, self.git_spec, True
                    )
                ]

                for file in files:
                    full_p = pathlib.Path(root) / file
                    rel_p = rel_root / file
                    if FileUtils.should_ignore(
                        file, rel_p, self.excludes, self.git_spec, False
                    ):
                        continue

                    try:
                        stat = full_p.stat()
                        sz = stat.st_size
                        if sz == 0:
                            continue
                        if sz not in size_map:
                            size_map[sz] = []
                        size_map[sz].append(full_p)
                    except Exception:
                        continue

            potential_groups = {s: p for s, p in size_map.items() if len(p) > 1}

            for size, paths in potential_groups.items():
                if self.stop_event.is_set():
                    return

                hash_sub_map: dict[str, list[pathlib.Path]] = {}
                for p in paths:
                    if self.stop_event.is_set():
                        return
                    h = self._get_hash(p)
                    if h:
                        if h not in hash_sub_map:
                            hash_sub_map[h] = []
                        hash_sub_map[h].append(p)

                for h, p_list in hash_sub_map.items():
                    if len(p_list) > 1:
                        self.result_queue.put(
                            {"hash": h, "size": size, "paths": [str(x) for x in p_list]}
                        )

            self.result_queue.put(("DONE", True))
            logger.info("AUDIT - Duplicate scan complete.")

        except Exception as e:
            logger.error(f"Duplicate scan failed: {e}")
            self.result_queue.put(("ERROR", str(e)))
