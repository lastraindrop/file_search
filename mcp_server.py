#!/usr/bin/env python3
"""FileCortex MCP Server.

A Model Context Protocol server providing file search and context
generation capabilities for AI assistants.
"""

import asyncio
import pathlib
from collections.abc import Callable

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
            """Initializes the fallback FastMCP mock."""
            self.name = name
            self._tools = {}

        def tool(self, name: str = None, description: str = "") -> Callable:
            """Registers a tool decorator."""
            def decorator(func):
                tool_name = name or func.__name__
                self._tools[tool_name] = {
                    "function": func,
                    "description": description or func.__doc__ or "",
                }
                return func
            return decorator

        def run(self, host: str = None, port: int = None) -> None:
            """Prints server info (mock)."""
            if host or port:
                print(
                    f"MCP Server would run on {host}:{port} "
                    f"with tools: {list(self._tools.keys())}"
                )
            else:
                print(f"MCP Server initialized with tools: {list(self._tools.keys())}")


_mcp_instance: FastMCP | None = None


def _ensure_tool_registry(mcp: FastMCP) -> FastMCP:
    """Adds a stable FileCortex tool registry to FastMCP instances.

    Recent MCP SDK versions no longer expose the private ``_tools`` attribute
    that the fallback mock has always provided. FileCortex keeps its own small
    registry for tests, fallback-mode diagnostics, and version-independent
    introspection while still delegating real registration to the SDK.
    """
    if getattr(mcp, "_filecortex_registry_wrapped", False):
        return mcp

    if not hasattr(mcp, "_tools"):
        mcp._tools = {}

    original_tool = mcp.tool

    def tool(name: str = None, description: str = "") -> Callable:
        sdk_decorator = original_tool(name=name, description=description)

        def decorator(func):
            tool_name = name or func.__name__
            mcp._tools[tool_name] = {
                "function": func,
                "description": description or func.__doc__ or "",
            }
            try:
                return sdk_decorator(func)
            except Exception:
                logger.warning(
                    "MCP SDK tool registration failed for '%s'. "
                    "The function is available for introspection but "
                    "not registered with the real SDK transport. "
                    "This usually indicates a version mismatch between "
                    "mcp and pydantic.",
                    tool_name,
                    exc_info=True,
                )
                return func

        return decorator

    mcp.tool = tool
    mcp._filecortex_registry_wrapped = True
    return mcp


def get_mcp() -> FastMCP:
    """Get or create the MCP server instance."""
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = _ensure_tool_registry(FastMCP("FileCortex"))
    return _mcp_instance

def get_dm() -> DataManager:
    """Returns a DataManager singleton instance."""
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

    # Align with the project's configured content-search size limit instead
    # of the module default, matching the Web/WS behavior.
    proj_data = get_dm().get_project_data(root)
    max_size = proj_data.get("max_search_size_mb", 10)

    def run_search() -> list[str]:
        results = []
        gen = search_generator(
            root,
            query,
            mode,
            manual_excludes=excludes,
            use_gitignore=True,
            stop_event=None,
            max_size_mb=max_size,
        )
        truncated = False
        for res in gen:
            results.append(f"{res['path']} ({res['match_type']})")
            if len(results) >= 50:
                truncated = True
                break
        if truncated:
            results.append(
                "(result list truncated at 50 entries; refine the query "
                "or use exact/regex mode to narrow the search)"
            )
        return results

    # Run the disk scan off the event loop so the MCP transport (stdio
    # heartbeats, cancellation, other tools) stays responsive.
    lines = await asyncio.to_thread(run_search)
    return "\n".join(lines) if lines else "No matches found."


@get_mcp().tool()
async def get_file_context(
    project_path: str,
    file_paths: list[str],
    fmt: str = "xml",
) -> str:
    """Retrieves the content of specified files formatted for LLM context.

    Args:
        project_path: The project root path.
        file_paths: List of file paths to retrieve.
        fmt: Output format - "xml" or "markdown".

    Returns:
        Formatted file contents as a string.
    """
    root = get_dm().resolve_project_root(project_path)
    if not root:
        return "Error: Unauthorized project path."

    # B8: surface dropped paths instead of silently returning fewer files
    # than requested, so the caller knows context was filtered for safety.
    safe_paths = [p for p in file_paths if PathValidator.is_safe(p, root)]
    dropped = len(file_paths) - len(safe_paths)
    prefix = ""
    if dropped:
        prefix = (
            f"Warning: {dropped} path(s) were outside the project root "
            f"and were skipped.\n\n"
        )

    fmt_norm = fmt.strip().lower()
    if fmt_norm == "xml":
        return prefix + ContextFormatter.to_xml(safe_paths, root_dir=root)
    return prefix + ContextFormatter.to_markdown(safe_paths, root_dir=root)


@get_mcp().tool()
async def list_workspaces() -> str:
    """Lists all registered workspaces and their pinned status.

    Returns:
        A formatted string listing all workspaces.
    """
    dm = get_dm()
    summary = dm.get_workspaces_summary()
    lines = ["Registered Workspaces:"]
    lines.extend(f"[Pin] {p['name']} - {p['path']}" for p in summary["pinned"])
    lines.extend(f"      {p['name']} - {p['path']}" for p in summary["recent"])
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
    try:
        validated = PathValidator.validate_project(project_path)
        path = str(validated)
    except FileNotFoundError as e:
        return f"Error: {e}"
    except NotADirectoryError as e:
        return f"Error: {e}"
    except PermissionError as e:
        return f"Error: {e}"

    root = get_dm().resolve_project_root(path)
    if root:
        return f"Workspace '{path}' is already registered."

    dm = get_dm()
    dm.add_to_recent(path)
    dm.get_project_data(path)
    if auto_pin:
        dm.toggle_pinned(path)
    dm.save()

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
        return FileUtils.generate_ascii_tree(
            pathlib.Path(root),
            excludes_str=excludes,
            use_gitignore=True,
            max_depth=max_depth,
        )
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
            logger.exception(f"MCP Stat error for {p}")
            lines.append(f"  {path.name}: Error retrieving stats")

    lines.append(f"\nTotal: {FormatUtils.format_size(total_size)}, {total_tokens} tokens")
    return "\n".join(lines)


def main() -> None:
    """Main entry point for MCP server."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="FileCortex MCP Server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse", "streamable-http", "http"],
        help=(
            "Transport type (default: stdio). 'sse' and 'streamable-http' "
            "are the MCP SDK names for network transports; 'http' is "
            "accepted as a legacy alias for 'streamable-http'."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transport")
    parser.add_argument("--port", type=int, default=3000, help="Port for HTTP transport")
    args = parser.parse_args()

    # Map the legacy alias onto the SDK literal before calling run().
    transport = "streamable-http" if args.transport == "http" else args.transport

    mcp_server = get_mcp()

    if _MCP_SDK_AVAILABLE:
        try:
            if transport == "stdio":
                mcp_server.run()
            else:
                mcp_server.run(
                    transport=transport, host=args.host, port=args.port
                )
            return
        except Exception as e:
            print(f"MCP SDK run failed: {e}", file=sys.stderr)
            sys.exit(1)

    # Mock fallback: print info and exit non-zero so callers know it's not live.
    print("FileCortex MCP Server — FALLBACK MODE (SDK not installed).", file=sys.stderr)
    print(f"Available tools: {list(mcp_server._tools.keys())}", file=sys.stderr)
    print("\nMCP SDK not installed. Install with:", file=sys.stderr)
    print('  pip install -e ".[mcp]"    (development)', file=sys.stderr)
    print('  pip install mcp             (runtime)', file=sys.stderr)
    print("\nServer NOT started. Exit code 2.", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
