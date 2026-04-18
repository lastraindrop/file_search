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
    _MCP_SDK_AVAILABLE = True
except ImportError:
    _MCP_SDK_AVAILABLE = False

    class FastMCP:
        """Fallback mock for environments without MCP SDK."""

        def __init__(self, name: str) -> None:
            self.name = name
            self._tools = {}

        def tool(self, name: str = None, description: str = ""):
            def decorator(func):
                tool_name = name or func.__name__
                self._tools[tool_name] = {
                    "function": func,
                    "description": description or func.__doc__ or "",
                }
                return func
            return decorator

        def run(self, host: str = None, port: int = None):
            if host or port:
                print(f"MCP Server would run on {host}:{port} with these tools: {list(self._tools.keys())}")
            else:
                print(f"MCP Server initialized with tools: {list(self._tools.keys())}")


_mcp_instance: FastMCP | None = None


def get_mcp() -> FastMCP:
    """Get or create the MCP server instance."""
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = FastMCP("FileCortex")
    return _mcp_instance

def get_dm():
    return DataManager()


@get_mcp().tool()
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
    root = get_dm().resolve_project_root(project_path)
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


@get_mcp().tool()
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
    root = get_dm().resolve_project_root(project_path)
    if not root:
        return "Error: Unauthorized project path."

    safe_paths = []
    for p in file_paths:
        if PathValidator.is_safe(p, root):
            safe_paths.append(p)

    if format == "xml":
        return ContextFormatter.to_xml(safe_paths, root_dir=root)
    return ContextFormatter.to_markdown(safe_paths, root_dir=root)


@get_mcp().tool()
async def list_workspaces() -> str:
    """Lists all registered workspaces and their pinned status.

    Returns:
        A formatted string listing all workspaces.
    """
    dm = get_dm()
    summary = dm.get_workspaces_summary()
    lines = ["Registered Workspaces:"]
    for p in summary["pinned"]:
        lines.append(f"[Pin] {p['name']} - {p['path']}")
    for p in summary["recent"]:
        lines.append(f"      {p['name']} - {p['path']}")
    return "\n".join(lines)


@get_mcp().tool()
async def register_workspace(
    project_path: str,
    auto_pin: bool = False,
) -> str:
    """Registers a new workspace/project path.

    Args:
        project_path: The project root path to register.
        auto_pin: Whether to pin the workspace (default: False).

    Returns:
        A confirmation message with the registered path.
    """
    path = PathValidator.norm_path(project_path)
    if not os.path.isdir(path):
        return f"Error: Path '{path}' does not exist or is not a directory."

    root = get_dm().resolve_project_root(project_path)
    if root:
        return f"Workspace '{project_path}' is already registered."

dm = get_dm()
    dm.add_to_recent(path)
    if auto_pin:
        dm.toggle_pinned(path)

    return f"Workspace '{path}' registered successfully."


@get_mcp().tool()
async def get_project_blueprint(
    project_path: str,
    max_depth: int = 3,
    excludes: str = "",
) -> str:
    """Generates ASCII tree blueprint of project structure.

    Args:
        project_path: The project root path.
        max_depth: Maximum depth to display (default: 3).
        excludes: Space-separated exclusion patterns.

    Returns:
        ASCII tree representation of the project.
    """
    from file_cortex_core import FileUtils

    root = get_dm().resolve_project_root(project_path)
    if not root:
        return "Error: Project path is not registered or authorized."

    try:
        tree = FileUtils.generate_ascii_tree(
            root,
            excludes_str=excludes,
            use_gitignore=True,
            max_depth=max_depth,
        )
        return tree
    except Exception as e:
        return f"Error generating blueprint: {e}"


@get_mcp().tool()
async def get_file_stats(
    project_path: str,
    file_paths: list[str],
) -> str:
    """Gets statistics for specified files.

    Args:
        project_path: The project root path.
        file_paths: List of file paths to get stats for.

    Returns:
        Statistics including size, tokens, and modified time.
    """
    from file_cortex_core import FormatUtils, NoiseReducer

    root = get_dm().resolve_project_root(project_path)
    if not root:
        return "Error: Project path is not registered or authorized."

    lines = ["File Statistics:"]
    total_size = 0
    total_tokens = 0

    for p in file_paths:
        if not PathValidator.is_safe(p, root):
            continue
        path = pathlib.Path(p)
        if not path.exists():
            continue

        try:
            stat = path.stat()
            size = stat.st_size
            total_size += size

            content = ""
            if path.is_file() and not FileUtils.is_binary(path):
                content = FileUtils.read_text_smart(path, max_bytes=1024 * 1024)
                tokens = FormatUtils.estimate_tokens(
                    NoiseReducer.clean(content)
                )
                total_tokens += tokens
            else:
                tokens = 0

            lines.append(
                f"  {path.name}: {FormatUtils.format_size(size)}, "
                f"{tokens} tokens, mtime={FormatUtils.format_datetime(stat.st_mtime)}"
            )
        except Exception:
            pass

    lines.append(f"\nTotal: {FormatUtils.format_size(total_size)}, {total_tokens} tokens")
    return "\n".join(lines)


def main() -> None:
    """Main entry point for MCP server."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="FileCortex MCP Server")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "http"],
                       help="Transport type (default: stdio)")
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transport")
    parser.add_argument("--port", type=int, default=3000, help="Port for HTTP transport")
    args = parser.parse_args()

    mcp_server = get_mcp()

    if _MCP_SDK_AVAILABLE:
        try:
            mcp_server.run(host=args.host, port=args.port)
            return
        except Exception as e:
            print(f"MCP SDK run failed: {e}", file=sys.stderr)

    print(f"FileCortex MCP Server initialized.")
    print(f"Available tools: {list(mcp_server._tools.keys())}")

    if not _MCP_SDK_AVAILABLE:
        print("\nNote: MCP SDK not installed. Install with:")
        print("  pip install mcp")
        print("\nFallback mode: Server initialized but not running.")
        print("To use with Claude Desktop, add this to your config:")
        print(
            '{ "mcpServers": { "file-cortex": { '
            '"command": "python", "args": ["' + os.path.abspath(__file__) + '"] } } }'
        )


if __name__ == "__main__":
    main()
