#!/usr/bin/env python3
"""FileCortex MCP Server.

A Model Context Protocol server providing file search and context
generation capabilities for AI assistants.
"""

import asyncio
import json
import os
import pathlib
from typing import Optional

from file_cortex_core import (
    ContextFormatter,
    DataManager,
    FileUtils,
    PathValidator,
    logger,
    search_generator,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:

    class FastMCP:
        """Fallback mock for environments without MCP SDK."""

        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self):
            return lambda x: x


mcp = FastMCP("FileCortex")
dm = DataManager()


@mcp.tool()
async def search_files(
    project_path: str,
    query: str,
    mode: str = "smart",
    excludes: str = "",
) -> str:
    """Search for files within a workspace using smart, exact, or regex modes.

    Args:
        project_path: The project root path to search within.
        query: The search query string.
        mode: Search mode - "smart", "exact", or "regex".
        excludes: Space-separated exclusion patterns.

    Returns:
        A string containing matching file paths and their match types.
    """
    root = dm.resolve_project_root(project_path)
    if not root:
        return f"Error: Project path '{project_path}' is not registered or authorized."

    results = []

    gen = search_generator(
        root,
        query,
        mode,
        manual_excludes=excludes,
        use_gitignore=True,
        stop_event=None,
    )

    for res in gen:
        results.append(f"{res['path']} ({res['match_type']})")
        if len(results) > 50:
            break

    return "\n".join(results) if results else "No matches found."


@mcp.tool()
async def get_file_context(
    project_path: str,
    file_paths: list[str],
    format: str = "xml",
) -> str:
    """Retrieves the content of specified files formatted for LLM context.

    Args:
        project_path: The project root path.
        file_paths: List of file paths to retrieve.
        format: Output format - "xml" or "markdown".

    Returns:
        Formatted file contents as a string.
    """
    root = dm.resolve_project_root(project_path)
    if not root:
        return "Error: Unauthorized project path."

    safe_paths = []
    for p in file_paths:
        if PathValidator.is_safe(p, root):
            safe_paths.append(p)

    if format == "xml":
        return ContextFormatter.to_xml(safe_paths, root_dir=root)
    return ContextFormatter.to_markdown(safe_paths, root_dir=root)


@mcp.tool()
async def list_workspaces() -> str:
    """Lists all registered workspaces and their pinned status.

    Returns:
        A formatted string listing all workspaces.
    """
    summary = dm.get_workspaces_summary()
    lines = ["Registered Workspaces:"]
    for p in summary["pinned"]:
        lines.append(f"[Pin] {p['name']} - {p['path']}")
    for p in summary["recent"]:
        lines.append(f"      {p['name']} - {p['path']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("FileCortex MCP Server Placeholder.")
    print("To use with Claude Desktop, add this to your config:")
    print(
        '{ "mcpServers": { "file-cortex": { '
        '"command": "python", "args": ["' + os.path.abspath(__file__) + '"] } } }'
    )
