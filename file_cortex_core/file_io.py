#!/usr/bin/env python3
"""File I/O utilities for FileCortex."""

import contextlib
import fnmatch
import os
import pathlib
import threading
from collections.abc import Generator
from functools import lru_cache
from typing import Any

import pathspec

from .config import logger
from .format_utils import FormatUtils


class FileUtils:
    """Utility class for file operations."""

    @staticmethod
    def walk_filtered(
        root: pathlib.Path,
        excludes: list[str],
        git_spec: pathspec.PathSpec | None = None,
        include_dirs: bool = False,
        stop_event: threading.Event | None = None,
        use_nested_gitignore: bool = True,
    ) -> Generator[tuple[pathlib.Path, pathlib.Path], None, None]:
        """Walks a project tree yielding filtered (full_path, rel_path) tuples.

        Directories are pruned based on ignore rules. Files are checked against
        the same ignore rules. Only non-ignored entries are yielded.

        When ``use_nested_gitignore`` is true (default) every ``.gitignore``
        along the path is applied with git's last-match-wins precedence, not
        just the root one. ``git_spec`` remains accepted for backwards
        compatibility and is used as the root spec when no .gitignore file is
        found on disk at the root.

        Args:
            root: Root directory to walk.
            excludes: Manual exclusion patterns.
            git_spec: Compiled gitignore spec (legacy root-only parameter).
            include_dirs: Whether to yield directory entries.
            stop_event: Optional threading.Event for early cancellation.
            use_nested_gitignore: Honor per-directory .gitignore files.

        Yields:
            Tuple of (full_path: pathlib.Path, rel_path: pathlib.Path).
        """
        root = pathlib.Path(root)
        for cur_root, dirs, files in os.walk(root):
            if stop_event is not None and stop_event.is_set():
                break

            cur_root_path = pathlib.Path(cur_root)
            try:
                rel_root = cur_root_path.relative_to(root)
            except (ValueError, RuntimeError):
                norm_root = os.path.normcase(os.path.abspath(cur_root))
                norm_base = os.path.normcase(os.path.abspath(root))
                if norm_root.startswith(norm_base):
                    rel_root = pathlib.Path(
                        norm_root[len(norm_base):].lstrip(os.sep)
                    )
                else:
                    rel_root = pathlib.Path(os.path.basename(cur_root))

            if use_nested_gitignore and git_spec is not None:
                chain = FileUtils.get_gitignore_chain(root, cur_root_path)
                if not chain and git_spec.patterns:
                    # No .gitignore files on disk (or only the root one was
                    # passed pre-compiled): keep legacy root-only behavior.
                    chain = [(root, git_spec)]
            else:
                chain = [(root, git_spec)] if git_spec else None

            def _ignored(
                name: str,
                full: pathlib.Path,
                rel: pathlib.Path,
                is_dir: bool,
                current_chain: list[tuple[pathlib.Path, pathspec.PathSpec]] | None = None,
            ) -> bool:
                if use_nested_gitignore and git_spec is not None:
                    return FileUtils._should_ignore_entry(
                        name, full, rel, excludes, current_chain, is_dir
                    )
                return FileUtils.should_ignore(name, rel, excludes, git_spec, is_dir)

            dirs[:] = [
                d
                for d in dirs
                if not _ignored(d, cur_root_path / d, rel_root / d, True, chain)
            ]

            if include_dirs:
                for d in dirs:
                    yield (cur_root_path / d, rel_root / d)

            for f in files:
                full_path = cur_root_path / f
                rel_path = rel_root / f
                if not _ignored(f, full_path, rel_path, False, chain):
                    yield (full_path, rel_path)

    @staticmethod
    def open_path_in_os(path: pathlib.Path) -> None:
        """Opens a file or directory using the default OS application.

        Args:
            path: Path to open.
        """
        import subprocess
        import sys

        p_str = str(path)
        try:
            if sys.platform == "win32":
                os.startfile(p_str)
            elif sys.platform == "darwin":
                subprocess.run(["open", p_str], check=True)
            else:
                subprocess.run(["xdg-open", p_str], check=True)
        except Exception:
            logger.exception(f"Failed to open path {p_str}")

    @staticmethod
    def is_binary(file_path: pathlib.Path) -> bool:
        """Determines if a file is binary based on content.

        Args:
            file_path: Path to check.

        Returns:
            True if file appears to be binary.
        """
        path = pathlib.Path(file_path)
        try:
            if not path.exists():
                return False
            if path.stat().st_size == 0:
                return False
        except Exception:
            return True

        text_exts = {
            ".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt",
            ".yml", ".yaml", ".xml", ".sql", ".c", ".cpp", ".h", ".java",
            ".go", ".rs", ".sh", ".bat", ".ini", ".cfg", ".toml", ".log",
            ".env", ".dockerfile",
        }
        if path.suffix.lower() in text_exts:
            return False

        try:
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
                if not chunk:
                    return False

                if b"\0" in chunk:
                    return True

                non_text_count = 0
                for byte in chunk:
                    if byte < 32 and byte not in (7, 8, 9, 10, 12, 13, 27):
                        non_text_count += 1

                return (non_text_count / len(chunk)) > 0.3
        except Exception:
            return True

    @staticmethod
    def clear_cache() -> None:
        """Clears the gitignore spec cache."""
        FileUtils._get_cached_gitignore_spec.cache_clear()

    @staticmethod
    def get_gitignore_spec(root_dir: pathlib.Path) -> pathspec.PathSpec:
        """Gets the .gitignore specification for a directory.

        Args:
            root_dir: Root directory to check.

        Returns:
            PathSpec object for gitignore patterns.
        """
        gitignore_path = pathlib.Path(root_dir) / ".gitignore"
        mtime = 0
        if gitignore_path.exists():
            with contextlib.suppress(Exception):
                mtime = gitignore_path.stat().st_mtime
        return FileUtils._get_cached_gitignore_spec(str(root_dir), mtime)

    @staticmethod
    @lru_cache(maxsize=256)
    def _get_cached_gitignore_spec(root_dir: str, mtime: float) -> pathspec.PathSpec:
        """Internal cached gitignore spec reader.

        Args:
            root_dir: Directory path.
            mtime: .gitignore modification time.

        Returns:
            Compiled PathSpec.
        """
        gitignore_path = pathlib.Path(root_dir) / ".gitignore"
        lines = []
        if gitignore_path.exists():
            try:
                with open(gitignore_path, encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                logger.warning(f"Failed to read gitignore at {gitignore_path}", exc_info=True)
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)

    @staticmethod
    def _dir_gitignore_spec(directory: pathlib.Path) -> pathspec.PathSpec:
        """Returns the compiled .gitignore spec for one directory.

        Returns an empty spec when the directory carries no .gitignore file so
        callers can treat the result uniformly.
        """
        gitignore_path = directory / ".gitignore"
        mtime = 0.0
        if gitignore_path.exists():
            with contextlib.suppress(Exception):
                mtime = gitignore_path.stat().st_mtime
        return FileUtils._get_cached_gitignore_spec(str(directory), mtime)

    @staticmethod
    def get_gitignore_chain(
        root_dir: pathlib.Path | str, target_dir: pathlib.Path | str
    ) -> list[tuple[pathlib.Path, pathspec.PathSpec]]:
        """Returns the nested .gitignore chain from root_dir down to target_dir.

        Git evaluates every .gitignore file along the directory path (parent
        rules first, child rules later). Each entry is a ``(base_dir, spec)``
        pair; patterns are relative to their own base directory. Rules in a
        child .gitignore can override parent rules, matching git semantics.

        Args:
            root_dir: Project root directory.
            target_dir: Directory whose chain is requested (inclusive).

        Returns:
            Ordered list of (base_dir, compiled_spec), parents first. Empty
            when no .gitignore exists along the path.
        """
        root = pathlib.Path(root_dir)
        target = pathlib.Path(target_dir)
        try:
            rel = target.relative_to(root)
        except ValueError:
            rel = pathlib.Path(".")
        chain: list[tuple[pathlib.Path, pathspec.PathSpec]] = []
        candidates = [root, *(root / part for part in rel.parts if part not in (".", ""))]
        for directory in candidates:
            spec = FileUtils._dir_gitignore_spec(directory)
            if spec.patterns:
                chain.append((directory, spec))
        return chain

    @staticmethod
    def _match_gitignore_chain(
        full_path: pathlib.Path | str,
        is_dir: bool,
        chain: list[tuple[pathlib.Path, pathspec.PathSpec]],
    ) -> bool:
        """Evaluates a path against a nested gitignore chain.

        Applies last-match-wins across the concatenation of all specs in the
        chain (parent files first), which is git's actual precedence rule.
        ``PathSpec.match_file()`` alone cannot express cross-file overrides
        (e.g. a child ``!error.log`` re-including a parent ``*.log``), so the
        individual patterns are evaluated in order instead.

        Args:
            full_path: Absolute path of the file/directory being tested.
            is_dir: Whether the path is a directory.
            chain: Ordered (base_dir, spec) pairs from get_gitignore_chain.

        Returns:
            True if the path is ignored by the effective rules.
        """
        abs_path = str(full_path)
        result = False
        for base, spec in chain:
            try:
                rel = os.path.relpath(abs_path, base).replace("\\", "/")
            except ValueError:
                continue
            if rel == ".." or rel.startswith("../"):
                continue
            if is_dir and not rel.endswith("/"):
                rel += "/"
            for pattern in spec.patterns:
                if pattern.include is not None and pattern.match_file(rel):
                    result = pattern.include
        return result

    @staticmethod
    def _should_ignore_entry(
        name: str,
        full_path: pathlib.Path | str,
        rel_path: pathlib.Path,
        manual_excludes: list[str],
        git_chain: list[tuple[pathlib.Path, pathspec.PathSpec]] | None,
        is_dir: bool,
    ) -> bool:
        """Manual excludes + nested gitignore chain in one check."""
        for pattern in manual_excludes:
            rel_posix = str(rel_path).replace("\\", "/")
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_posix, pattern):
                return True
        if git_chain:
            return FileUtils._match_gitignore_chain(full_path, is_dir, git_chain)
        return False

    @staticmethod
    def should_ignore(
        name: str,
        rel_path: pathlib.Path,
        manual_excludes: list[str],
        git_spec: pathspec.PathSpec | None = None,
        is_dir: bool = False,
    ) -> bool:
        """Checks if a file or directory should be ignored.

        Args:
            name: File/directory name.
            rel_path: Relative path.
            manual_excludes: Manual exclusion patterns.
            git_spec: Gitignore specification.
            is_dir: Whether this is a directory.

        Returns:
            True if should be ignored.
        """
        for pattern in manual_excludes:
            # Manual patterns follow gitignore-style "/" separators (e.g.
            # "docs/*"), but str(rel_path) yields "\" on Windows. Normalize
            # so sub-path patterns work identically on every platform.
            rel_posix = str(rel_path).replace("\\", "/")
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_posix, pattern):
                return True
        if git_spec:
            path_str = str(rel_path).replace(os.sep, "/")
            if is_dir and not path_str.endswith("/"):
                path_str += "/"
            if git_spec.match_file(path_str):
                return True
        return False

    @staticmethod
    def get_project_items(
        root_dir: str,
        manual_excludes: list[str],
        use_gitignore: bool = True,
        mode: str = "files",
    ) -> list[str]:
        """Gets project files or folders based on mode.

        Args:
            root_dir: Root directory to scan.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.
            mode: 'files' or 'top_folders'.

        Returns:
            List of paths.
        """
        root = pathlib.Path(root_dir).resolve()
        git_spec = FileUtils.get_gitignore_spec(root) if use_gitignore else None
        results = []

        if mode == "top_folders":
            for item in root.iterdir():
                rel = item.relative_to(root)
                if not FileUtils.should_ignore(
                    item.name, rel, manual_excludes, git_spec, item.is_dir()
                ):
                    results.append(str(item))
        else:
            for full_path, _rel_path in FileUtils.walk_filtered(
                root, manual_excludes, git_spec, include_dirs=False
            ):
                results.append(str(full_path))
        return results

    @staticmethod
    def flatten_paths(
        paths: list[str],
        root_dir: str | None = None,
        manual_excludes: list[str] | None = None,
        use_gitignore: bool = True,
        stop_event: threading.Event | None = None,
    ) -> list[str]:
        """Expands directories to files recursively.

        Args:
            paths: List of paths to expand.
            root_dir: Root directory for reference.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.
            stop_event: Optional threading.Event to cancel expansion.

        Returns:
            Sorted list of unique file paths.
        """
        if not paths:
            return []
        unique_files = set()
        root = pathlib.Path(root_dir).resolve() if root_dir else None
        git_spec = (
            FileUtils.get_gitignore_spec(root)
            if (root and use_gitignore)
            else None
        )
        excludes = manual_excludes or []

        for p_str in paths:
            p = pathlib.Path(p_str).resolve()
            if not p.exists():
                continue

            if p.is_file():
                unique_files.add(str(p))
            elif p.is_dir():
                for curr_root, dirs, files in os.walk(p):
                    if stop_event is not None and stop_event.is_set():
                        break

                    curr_root_path = pathlib.Path(curr_root).resolve()
                    chain = (
                        FileUtils.get_gitignore_chain(root, curr_root_path)
                        if (root and use_gitignore)
                        else None
                    )
                    if root and use_gitignore and not chain and git_spec and git_spec.patterns:
                        chain = [(root, git_spec)]

                    valid_dirs = []
                    for d in dirs:
                        d_path = curr_root_path / d
                        if root:
                            if root == d_path:
                                rel = pathlib.Path(".")
                            elif root in d_path.parents:
                                rel = d_path.relative_to(root)
                            else:
                                rel = d_path

                            if not FileUtils._should_ignore_entry(
                                d, d_path, rel, excludes, chain, True
                            ):
                                valid_dirs.append(d)
                        else:
                            if not FileUtils.should_ignore(
                                d, d_path, excludes, git_spec, True
                            ):
                                valid_dirs.append(d)
                    dirs[:] = valid_dirs

                    for f in files:
                        f_path = curr_root_path / f

                        is_rel = False
                        try:
                            if root:
                                if hasattr(f_path, "is_relative_to"):
                                    is_rel = f_path.is_relative_to(root)
                                else:
                                    is_rel = root == f_path or root in f_path.parents
                        except Exception:
                            pass

                        rel = f_path.relative_to(root) if (root and is_rel) else f_path
                        if not FileUtils._should_ignore_entry(
                            f, f_path, rel, excludes, chain, False
                        ):
                            unique_files.add(str(f_path))

        return sorted(unique_files)

    @staticmethod
    @lru_cache(maxsize=128)
    def _detect_encoding(file_path_str: str, mtime: float, size: int) -> str:
        """Internal cached encoding detector.

        Args:
            file_path_str: File path string.
            mtime: Modification time.
            size: File size.

        Returns:
            Detected encoding string.
        """
        try:
            from charset_normalizer import from_bytes

            with open(file_path_str, "rb") as f:
                header = f.read(65536)
                best_match = from_bytes(header).best()
                return (
                    best_match.encoding
                    if (best_match and best_match.encoding)
                    else "utf-8"
                )
        except Exception:
            return "utf-8"

    @staticmethod
    def read_text_smart(file_path: pathlib.Path, max_bytes: int | None = None) -> str:
        """Reads file content with smart encoding detection.

        Args:
            file_path: Path to the file.
            max_bytes: Maximum bytes to read.

        Returns:
            File content as string.
        """
        try:
            if not file_path.exists() or not file_path.is_file():
                return ""

            # Guard against negative limits: f.read(-1) would slurp the
            # entire file, the exact opposite of the caller's intent.
            if max_bytes is not None and max_bytes <= 0:
                return ""

            st = file_path.stat()
            # If max_bytes is set and file is huge, read_text_smart must still be efficient
            encoding = FileUtils._detect_encoding(
                str(file_path.absolute()), st.st_mtime, st.st_size
            )

            with open(file_path, "rb") as f:
                if max_bytes:
                    raw = f.read(max_bytes)
                    try:
                        return raw.decode(encoding, errors="ignore")
                    except Exception:
                        return raw.decode("utf-8", errors="ignore")
                else:
                    return f.read().decode(encoding, errors="ignore")
        except Exception as e:
            logger.debug(f"Smart read failed for {file_path}: {e}")

        # Final safety fallback using rb and decode to respect max_bytes
        try:
            with open(file_path, "rb") as f:
                if max_bytes:
                    return f.read(max_bytes).decode("utf-8", errors="ignore")
                return f.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

    @staticmethod
    def get_language_tag(suffix: str) -> str:
        """Gets the language tag for a file extension.

        Args:
            suffix: File suffix including dot.

        Returns:
            Language identifier string.
        """
        mapping = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".html": "html",
            ".css": "css", ".json": "json", ".md": "markdown",
            ".java": "java", ".c": "c", ".cpp": "cpp", ".h": "cpp",
            ".cs": "csharp", ".rs": "rust", ".go": "go", ".sql": "sql",
            ".xml": "xml", ".sh": "bash", ".bat": "batch", ".yml": "yaml",
            ".yaml": "yaml", ".toml": "toml", ".dockerfile": "dockerfile",
            "dockerfile": "dockerfile", ".vue": "vue", ".svelte": "svelte",
            ".php": "php", ".rb": "ruby", ".swift": "swift", ".kt": "kotlin",
            ".dart": "dart", ".ini": "ini", ".cfg": "ini", ".log": "text",
        }
        return mapping.get(suffix.lower(), "")

    @staticmethod
    def get_metadata(path_obj: pathlib.Path) -> dict[str, Any]:
        """Gets metadata for a file or directory.

        Args:
            path_obj: Path to get metadata for.

        Returns:
            Dictionary with metadata fields.
        """
        try:
            p = pathlib.Path(path_obj).resolve()
            stat = p.stat()
            return {
                "name": p.name,
                "path": str(p),
                "abs_path": str(p),
                "type": "dir" if p.is_dir() else "file",
                "size": stat.st_size,
                "size_fmt": FormatUtils.format_size(stat.st_size),
                "mtime": stat.st_mtime,
                "mtime_fmt": FormatUtils.format_datetime(stat.st_mtime),
                "ext": p.suffix.lower(),
            }
        except Exception:
            # Fallback shape must carry the full contract of the success
            # branch: downstream consumers (e.g. ws_routes search frames)
            # index keys like "path"/"type" directly.
            fallback_name = pathlib.Path(path_obj).name
            return {
                "name": fallback_name,
                "path": str(path_obj),
                "abs_path": str(path_obj),
                "type": "file",
                "size": 0,
                "size_fmt": FormatUtils.format_size(0),
                "mtime": 0,
                "mtime_fmt": FormatUtils.format_datetime(0),
                "ext": pathlib.Path(path_obj).suffix.lower(),
            }

    @staticmethod
    def generate_ascii_tree(
        root_dir: pathlib.Path,
        excludes_str: str,
        use_gitignore: bool = True,
        max_depth: int = 15,
    ) -> str:
        """Generates an ASCII tree representation of a directory.

        Args:
            root_dir: Root directory to tree.
            excludes_str: Exclusion patterns string.
            use_gitignore: Whether to respect .gitignore.
            max_depth: Maximum tree depth.

        Returns:
            ASCII tree string.
        """
        root_dir = pathlib.Path(root_dir)
        lines = [f"Project: {root_dir.name}"]
        excludes = [e.strip() for e in excludes_str.split() if e.strip()]
        git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None

        def _build_tree(
            path: pathlib.Path,
            prefix: str = "",
            depth: int = 0,
        ) -> None:
            if depth > max_depth:
                lines.append(f"{prefix}└── [Max Depth Reached ({max_depth}) ...]")
                return
            try:
                chain = None
                if use_gitignore:
                    chain = FileUtils.get_gitignore_chain(root_dir, path)
                    if not chain and git_spec and git_spec.patterns:
                        chain = [(root_dir, git_spec)]
                with os.scandir(path) as it:
                    entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                valid_entries = []
                for entry in entries:
                    rel_path = pathlib.Path(entry.path).relative_to(root_dir)
                    if not FileUtils._should_ignore_entry(
                        entry.name, entry.path, rel_path, excludes, chain, entry.is_dir()
                    ):
                        valid_entries.append(entry)

                for i, entry in enumerate(valid_entries):
                    is_last = i == len(valid_entries) - 1
                    connector = "└── " if is_last else "├── "
                    lines.append(f"{prefix}{connector}{entry.name}")
                    if entry.is_dir():
                        new_prefix = prefix + ("    " if is_last else "│   ")
                        _build_tree(entry.path, new_prefix, depth + 1)
            except PermissionError:
                logger.warning(f"Permission denied: {path}")
            except Exception:
                logger.exception(f"Tree generation error at {path}")

        try:
            _build_tree(root_dir)
        except Exception:
            logger.exception("Tree generation failed")
        return "\n".join(lines)
