#!/usr/bin/env python3
"""Duplicate file detection module.

Finds duplicate files based on size and SHA256 hash comparison.
"""

import hashlib
import pathlib
import queue
import threading

from .config import logger
from .file_io import FileUtils


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
        super().__init__(daemon=True)
        self.root_dir = pathlib.Path(root_dir)
        self.excludes = [
            e.lower().strip() for e in manual_excludes.split() if e.strip()
        ]
        self.git_spec = (
            FileUtils.get_gitignore_spec(self.root_dir) if use_gitignore else None
        )
        self.result_queue = result_queue
        self.stop_event = stop_event

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
        except Exception:
            logger.exception(f"Hashing failed for {file_path}")
            return None

    def run(self) -> None:
        """Main worker loop that scans for duplicates."""
        logger.info(f"AUDIT - Starting duplicate scan in {self.root_dir}")
        size_map: dict[int, list[pathlib.Path]] = {}

        try:
            for full_p, _rel_p in FileUtils.walk_filtered(
                self.root_dir, self.excludes, self.git_spec,
                include_dirs=False, stop_event=self.stop_event,
            ):
                if self.stop_event.is_set():
                    return

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
            logger.exception("Duplicate scan failed")
            self.result_queue.put(("ERROR", str(e)))
