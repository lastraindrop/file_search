#!/usr/bin/env python3
"""Context generation and noise reduction for FileCortex.
"""

import pathlib

from .config import logger
from .file_io import FileUtils


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
        include_blueprint: bool = True,
    ) -> str:
        """Converts files to XML format with CDATA and optional blueprint.

        Args:
            paths: List of file paths.
            root_dir: Root directory.
            prompt_prefix: Optional prefix to add.
            manual_excludes: Exclusion patterns.
            use_gitignore: Whether to respect .gitignore.
            include_blueprint: Whether to include project structure blueprint.

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
        
        if include_blueprint and root:
            ex_str = " ".join(manual_excludes) if manual_excludes else ""
            blueprint = ContextFormatter.generate_blueprint(str(root), ex_str, use_gitignore)
            blocks.append("<blueprint>\n<![CDATA[\n")
            blocks.append(blueprint)
            blocks.append("\n]]>\n</blueprint>\n\n")

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
