#!/usr/bin/env python3
"""Formatting utilities for FileCortex.
"""

import datetime
import pathlib
from typing import Any

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
        if size_bytes < 0:
            return "0 B"
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
