#!/usr/bin/env python3
"""Utility modules for FileCortex.

Provides file operations, formatting utilities, and context generation.
"""

import datetime
import fnmatch
import os
import pathlib
from functools import lru_cache
from typing import Any

import pathspec

from .config import logger


class FormatUtils:
    """Utility class for formatting values."""

    @staticmethod
    def format_number(val: float | int) -> str:
        """Formats a number with thousands separator.

        Args:
            val: The number to format.

        Returns:
            Formatted string with comma separators.
        """
        try:
            return f"{int(val):,}"
        except (ValueError, TypeError):
            return str(val)

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Formats a byte size into human-readable string.

        Args:
            size_bytes: Size in bytes.

        Returns:
            Formatted size string (B, KB, MB, GB).
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def format_datetime(mtime: float) -> str:
        """Formats a timestamp into a readable date-time string.

        Args:
            mtime: Unix timestamp.

        Returns:
            Formatted date-time string.
        """
        try:
            return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimates token count for text content.

        Uses weighted calculation:
        - ASCII/Latin characters: ~4 chars per token
        - Non-ASCII (CJK/Unicode): ~1.5 chars per token

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        non_ascii = sum(1 for c in text if ord(c) > 127)
        ascii_count = len(text) - non_ascii
        return int((ascii_count / 4) + (non_ascii / 1.5))

    @staticmethod
    def collect_paths(
        paths: list[str],
        root_dir: str | None = None,
        mode: str = "relative",
        separator: str = "\n",
        file_prefix: str = "",
        dir_suffix: str = "",
    ) -> str:
        """Formats paths into a single string with custom separators.

        Args:
            paths: List of paths to format.
            root_dir: Root directory for relative paths.
            mode: Path mode ('relative' or 'absolute').
            separator: Separator between paths.
            file_prefix: Prefix to add to all paths.
            dir_suffix: Suffix to add to directory paths.

        Returns:
            Formatted paths string.
        """
        sep = separator.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")

        formatted = []
        root = pathlib.Path(root_dir).resolve() if root_dir else None

        for p_str in paths:
            try:
                p = pathlib.Path(p_str).resolve()
                is_dir = p.is_dir()

                if mode == "relative" and root:
                    if root in p.parents or root == p:
                        final_p_str = str(p.relative_to(root))
                    else:
                        final_p_str = str(p)
                else:
                    final_p_str = str(p)

                if is_dir:
                    if dir_suffix and not final_p_str.endswith(dir_suffix):
                        final_p_str += dir_suffix

                final_p_str = file_prefix + final_p_str

                formatted.append(final_p_str)
            except Exception:
                formatted.append(p_str)

        return sep.join(formatted)


class FileUtils:
    """Utility class for file operations."""

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
        except Exception as e:
            logger.error(f"Failed to open path {p_str}: {e}")

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
            ".py",
            ".js",
            ".ts",
            ".html",
            ".css",
            ".json",
            ".md",
            ".txt",
            ".yml",
            ".yaml",
            ".xml",
            ".sql",
            ".c",
            ".cpp",
            ".h",
            ".java",
            ".go",
            ".rs",
            ".sh",
            ".bat",
            ".ini",
            ".cfg",
            ".toml",
            ".log",
            ".env",
            ".dockerfile",
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

                if (non_text_count / len(chunk)) > 0.3:
                    return True
                return False
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
            try:
                mtime = gitignore_path.stat().st_mtime
            except Exception:
                pass
        return FileUtils._get_cached_gitignore_spec(str(root_dir), mtime)

    @staticmethod
    @lru_cache(maxsize=32)
    def _get_cached_gitignore_spec(root_dir: str, mtime: float) -> pathspec.PathSpec:
        """Internal cached gitignore spec reader.

        Args:
            root_dir: Root directory path.
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
            except Exception as e:
                logger.warning(f"Failed to read gitignore at {gitignore_path}: {e}")
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)

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
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(
                str(rel_path), pattern
            ):
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
        git_spec = FileUtils.get_gitignore_spec(str(root)) if use_gitignore else None
        results = []

        if mode == "top_folders":
            for item in root.iterdir():
                rel = item.relative_to(root)
                if not FileUtils.should_ignore(
                    item.name, rel, manual_excludes, git_spec, item.is_dir()
                ):
                    results.append(str(item))
        else:
            for curr_root, dirs, files in os.walk(root):
                curr_root_path = pathlib.Path(curr_root)
                dirs[:] = [
                    d
                    for d in dirs
                    if not FileUtils.should_ignore(
                        d,
                        (curr_root_path / d).relative_to(root),
                        manual_excludes,
                        git_spec,
                        True,
                    )
                ]
                for f in files:
                    rel = (curr_root_path / f).relative_to(root)
                    if not FileUtils.should_ignore(
                        f, rel, manual_excludes, git_spec, False
                    ):
                        results.append(str(curr_root_path / f))
        return results

    @staticmethod
    def flatten_paths(
        paths: list[str],
        root_dir: str | None = None,
        manual_excludes: list[str] | None = None,
        use_gitignore: bool = True,
    ) -> list[str]:
        """Expands directories to files recursively.

        Args:
            paths: List of paths to expand.
            root_dir: Root directory for reference.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.

        Returns:
            Sorted list of unique file paths.
        """
        if not paths:
            return []
        unique_files = set()
        root = pathlib.Path(root_dir).resolve() if root_dir else None
        git_spec = (
            FileUtils.get_gitignore_spec(str(root))
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
                    curr_root_path = pathlib.Path(curr_root).resolve()

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

                            if not FileUtils.should_ignore(
                                d, rel, excludes, git_spec, True
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
                        if not FileUtils.should_ignore(
                            f, rel, excludes, git_spec, False
                        ):
                            unique_files.add(str(f_path))

        return sorted(unique_files)

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
            from charset_normalizer import from_bytes

            with open(file_path, "rb") as f:
                header = f.read(65536)

                best_match = from_bytes(header).best()
                encoding = (
                    best_match.encoding
                    if (best_match and best_match.encoding)
                    else "utf-8"
                )

                f.seek(0)

                if max_bytes:
                    raw = f.read(max_bytes + 10)
                    try:
                        return raw.decode(encoding, errors="ignore")[:max_bytes]
                    except Exception:
                        return raw.decode("utf-8", errors="ignore")[:max_bytes]
                else:
                    return f.read().decode(encoding, errors="ignore")
        except Exception as e:
            logger.debug(f"Smart read failed for {file_path}: {e}")

        content = file_path.read_text("utf-8", "ignore")
        return content[:max_bytes] if max_bytes else content

    @staticmethod
    def get_language_tag(suffix: str) -> str:
        """Gets the language tag for a file extension.

        Args:
            suffix: File suffix including dot.

        Returns:
            Language identifier string.
        """
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".md": "markdown",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "cpp",
            ".cs": "csharp",
            ".rs": "rust",
            ".go": "go",
            ".sql": "sql",
            ".xml": "xml",
            ".sh": "bash",
            ".bat": "batch",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".toml": "toml",
            ".dockerfile": "dockerfile",
            "dockerfile": "dockerfile",
            ".vue": "vue",
            ".svelte": "svelte",
            ".php": "php",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
            ".dart": "dart",
            ".ini": "ini",
            ".cfg": "ini",
            ".log": "text",
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
            return {
                "size": 0,
                "mtime": 0,
                "ext": "",
                "abs_path": str(path_obj),
                "name": pathlib.Path(path_obj).name,
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
        excludes = [e.lower().strip() for e in excludes_str.split() if e.strip()]
        git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None

        def _build_tree(path: pathlib.Path, prefix: str = "", depth: int = 0) -> None:
            if depth > max_depth:
                lines.append(f"{prefix}└── [Max Depth Reached ({max_depth}) ...]")
                return
            try:
                with os.scandir(path) as it:
                    entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                valid_entries = []
                for entry in entries:
                    rel_path = pathlib.Path(entry.path).relative_to(root_dir)
                    if not FileUtils.should_ignore(
                        entry.name, rel_path, excludes, git_spec
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
            except Exception as e:
                logger.error(f"Tree generation error at {path}: {e}")

        try:
            _build_tree(root_dir)
        except Exception as e:
            logger.error(f"Tree generation failed: {e}")
        return "\n".join(lines)


class NoiseReducer:
    """Cleans code context to reduce token noise."""

    @staticmethod
    def clean(content: str, max_line_length: int = 500) -> str:
        """Cleans content by removing minified blocks and noise.

        Args:
            content: Text content to clean.
            max_line_length: Maximum line length before skipping.

        Returns:
            Cleaned content string.
        """
        if content is None:
            return ""

        lines = content.splitlines()
        cleaned_lines = []

        for line in lines:
            if len(line) > max_line_length:
                cleaned_lines.append(
                    f"[... Line of {len(line)} chars skipped by NoiseReducer ...]"
                )
                continue

            if len(line) > 200 and not any(c.isspace() for c in line):
                total = len(line)
                alnum = sum(1 for c in line if c.isalnum() or c in "+/=")
                if (alnum / total) > 0.95:
                    cleaned_lines.append(
                        f"[... Base64-like block of {total} chars skipped ...]"
                    )
                    continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)


class ContextFormatter:
    """Formats file contents for LLM context."""

    @staticmethod
    def to_markdown(
        paths: list[str],
        root_dir: str | None = None,
        prompt_prefix: str | None = None,
        manual_excludes: list[str] | None = None,
        use_gitignore: bool = True,
    ) -> str:
        """Converts files to markdown format.

        Args:
            paths: List of file paths.
            root_dir: Root directory.
            prompt_prefix: Optional prefix to add.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.

        Returns:
            Markdown formatted string.
        """
        all_files = FileUtils.flatten_paths(
            paths, root_dir, manual_excludes, use_gitignore
        )

        blocks = []
        if prompt_prefix:
            blocks.append(f"{prompt_prefix}\n\n---\n\n")

        root = pathlib.Path(root_dir).resolve() if root_dir else None

        for f_str in all_files:
            p = pathlib.Path(f_str)
            if not p.exists() or not p.is_file() or FileUtils.is_binary(p):
                continue

            try:
                p_res = p.resolve()
                rel_path = (
                    p_res.relative_to(root)
                    if root and (root == p_res or root in p_res.parents)
                    else p.name
                )
                lang = FileUtils.get_language_tag(p.suffix)
                stat = p.stat()
                size_kb = stat.st_size / 1024

                content = FileUtils.read_text_smart(p, max_bytes=1024 * 1024)
                content = NoiseReducer.clean(content)

                header = f"File: {rel_path} ({size_kb:.1f} KB)\n"
                blocks.append(f"{header}```{lang}\n{content}\n```\n\n")
            except Exception as e:
                logger.error(f"Failed to format file {f_str} for context: {e}")

        return "".join(blocks)

    @staticmethod
    def to_xml(
        paths: list[str],
        root_dir: str | None = None,
        prompt_prefix: str | None = None,
        manual_excludes: list[str] | None = None,
        use_gitignore: bool = True,
    ) -> str:
        """Converts files to XML format with CDATA.

        Args:
            paths: List of file paths.
            root_dir: Root directory.
            prompt_prefix: Optional prefix to add.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.

        Returns:
            XML formatted string.
        """
        all_files = FileUtils.flatten_paths(
            paths, root_dir, manual_excludes, use_gitignore
        )

        blocks = []
        if prompt_prefix:
            blocks.append(f"<instruction>\n{prompt_prefix}\n</instruction>\n\n")

        root = pathlib.Path(root_dir).resolve() if root_dir else None
        blocks.append("<context>\n")

        for f_str in all_files:
            p = pathlib.Path(f_str)
            if not p.exists() or not p.is_file() or FileUtils.is_binary(p):
                continue

            try:
                p_res = p.resolve()
                rel_path = (
                    p_res.relative_to(root)
                    if root and (root == p_res or root in p_res.parents)
                    else p.name
                )
                size_kb = p.stat().st_size / 1024

                content = FileUtils.read_text_smart(p, max_bytes=1024 * 1024)
                content = NoiseReducer.clean(content)

                safe_content = content.replace("]]>", "]]]]><![CDATA[>")

                blocks.append(
                    f'  <file path="{rel_path}" size="{size_kb:.1f}KB">\n'
                    f"<![CDATA[\n{safe_content}\n]]>\n  </file>\n"
                )
            except Exception:
                pass

        blocks.append("</context>")
        return "".join(blocks)

    @staticmethod
    def generate_blueprint(
        root_dir: str, excludes_str: str, use_gitignore: bool = True
    ) -> str:
        """Generates a project blueprint (ASCII tree).

        Args:
            root_dir: Root directory.
            excludes_str: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.

        Returns:
            Blueprint string.
        """
        tree = FileUtils.generate_ascii_tree(
            root_dir, excludes_str, use_gitignore, max_depth=5
        )
        return f"--- PROJECT BLUEPRINT ---\n\n{tree}\n"
