#!/usr/bin/env python3
"""Context generation and noise reduction for FileCortex."""

import pathlib
from typing import Final

from .config import logger
from .file_io import FileUtils

MAX_EXPORT_FILES: Final = 500
MAX_TOTAL_CONTENT_BYTES: Final = 50 * 1024 * 1024  # 50 MB


class NoiseReducer:
    """Cleans code context to reduce token noise."""

    @staticmethod
    def clean(content: str | None, max_line_length: int = 500) -> str:
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
        apply_noise_reducer: bool = False,
        max_files: int = MAX_EXPORT_FILES,
    ) -> str:
        """Converts files to markdown format.

        Args:
            paths: List of file paths.
            root_dir: Root directory.
            prompt_prefix: Optional prefix to add.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.
            apply_noise_reducer: Whether to apply noise reduction to content.
            max_files: Maximum number of files to include (OOM protection).

        Returns:
            Markdown formatted string.
        """
        all_files = FileUtils.flatten_paths(
            paths, root_dir, manual_excludes, use_gitignore
        )

        if len(all_files) > max_files:
            logger.warning(
                f"Export truncated: {len(all_files)} files found, "
                f"limiting to {max_files}."
            )
            all_files = all_files[:max_files]

        blocks = []
        total_bytes = 0
        if prompt_prefix:
            blocks.append(f"{prompt_prefix}\n\n---\n\n")

        root = pathlib.Path(root_dir).resolve() if root_dir else None

        for f_str in all_files:
            if total_bytes >= MAX_TOTAL_CONTENT_BYTES:
                logger.warning(
                    f"Export truncated at {total_bytes} bytes "
                    f"(limit: {MAX_TOTAL_CONTENT_BYTES})."
                )
                blocks.append(
                    f"\n> [Export truncated: reached {MAX_TOTAL_CONTENT_BYTES // (1024*1024)}MB "
                    f"content limit. {len(all_files) - len(blocks)} files skipped.]\n"
                )
                break

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
                if apply_noise_reducer:
                    content = NoiseReducer.clean(content)

                total_bytes += len(content.encode("utf-8", errors="replace"))
                header = f"File: {rel_path} ({size_kb:.1f} KB)\n"
                blocks.append(f"{header}```{lang}\n{content}\n```\n\n")
            except Exception:
                logger.exception(f"Failed to format file {f_str} for context")

        return "".join(blocks)

    @staticmethod
    def to_xml(
        paths: list[str],
        root_dir: str | None = None,
        prompt_prefix: str | None = None,
        manual_excludes: list[str] | None = None,
        use_gitignore: bool = True,
        include_blueprint: bool = True,
        apply_noise_reducer: bool = True,
        max_files: int = MAX_EXPORT_FILES,
    ) -> str:
        """Converts files to XML format with CDATA and optional blueprint.

        Args:
            paths: List of file paths.
            root_dir: Root directory.
            prompt_prefix: Optional prefix to add.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.
            include_blueprint: Whether to include project structure blueprint.
            apply_noise_reducer: Whether to apply noise reduction to content.
            max_files: Maximum number of files to include (OOM protection).

        Returns:
            XML formatted string.
        """
        all_files = FileUtils.flatten_paths(
            paths, root_dir, manual_excludes, use_gitignore
        )

        if len(all_files) > max_files:
            logger.warning(
                f"Export truncated: {len(all_files)} files found, "
                f"limiting to {max_files}."
            )
            all_files = all_files[:max_files]

        blocks = []
        total_bytes = 0
        if prompt_prefix:
            blocks.append(f"<instruction>\n{prompt_prefix}\n</instruction>\n\n")

        root = pathlib.Path(root_dir).resolve() if root_dir else None

        if include_blueprint and root:
            ex_str = " ".join(manual_excludes) if manual_excludes else ""
            blueprint = ContextFormatter.generate_blueprint(str(root), ex_str, use_gitignore)
            blocks.append("<blueprint>\n<![CDATA[\n")
            blocks.append(blueprint)
            blocks.append("\n]]>\n</blueprint>\n\n")

        blocks.append("<context>\n")

        for f_str in all_files:
            if total_bytes >= MAX_TOTAL_CONTENT_BYTES:
                logger.warning(
                    f"Export truncated at {total_bytes} bytes "
                    f"(limit: {MAX_TOTAL_CONTENT_BYTES})."
                )
                blocks.append(
                    f"  <!-- Export truncated: reached "
                    f"{MAX_TOTAL_CONTENT_BYTES // (1024*1024)}MB limit. -->\n"
                )
                break

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
                if apply_noise_reducer:
                    content = NoiseReducer.clean(content)

                total_bytes += len(content.encode("utf-8", errors="replace"))

                safe_content = content.replace("]]>", "]]]]><![CDATA[>")

                blocks.append(
                    f'  <file path="{rel_path}" size="{size_kb:.1f}KB">\n'
                    f"<![CDATA[\n{safe_content}\n]]>\n  </file>\n"
                )
            except Exception:
                logger.exception(f"Failed to format file {f_str} for XML context")

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
