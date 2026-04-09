import asyncio
import json
import os
import pathlib
from typing import Optional
from file_cortex_core import DataManager, FileUtils, search_generator, ContextFormatter, PathValidator, logger

# mcp-sdk is required for this to run as a formal server
# pip install mcp
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Fallback/Mock for environment compatibility check
    class FastMCP:
        def __init__(self, name): self.name = name
        def tool(self): return lambda x: x

mcp = FastMCP("FileCortex")
dm = DataManager()

@mcp.tool()
async def search_files(
    project_path: str,
    query: str,
    mode: str = "smart",
    excludes: str = ""
) -> str:
    """
    Search for files within a workspace using smart, exact, or regex modes.
    Returns a list of matching file paths and their metadata.
    """
    root = dm.resolve_project_root(project_path)
    if not root:
        return f"Error: Project path '{project_path}' is not registered or authorized."
    
    stop_event = asyncio.Event() # Mock stop event for generator
    results = []
    
    # Run search_generator in the shared pool or directly if it's non-blocking enough
    gen = search_generator(
        root, query, mode, manual_excludes=excludes, 
        use_gitignore=True, stop_event=None
    )
    
    for res in gen:
        results.append(f"{res['path']} ({res['match_type']})")
        if len(results) > 50: break
        
    return "\n".join(results) if results else "No matches found."

@mcp.tool()
async def get_file_context(
    project_path: str,
    file_paths: list[str],
    format: str = "xml"
) -> str:
    """
    Retrieves the content of specified files formatted for LLM context.
    'format' can be 'xml' or 'markdown'.
    """
    root = dm.resolve_project_root(project_path)
    if not root:
        return "Error: Unauthorized project path."
    
    # Security validation
    safe_paths = []
    for p in file_paths:
        if PathValidator.is_safe(p, root):
            safe_paths.append(p)
            
    if format == "xml":
        return ContextFormatter.to_xml(safe_paths, root_dir=root)
    return ContextFormatter.to_markdown(safe_paths, root_dir=root)

@mcp.tool()
async def list_workspaces() -> str:
    """Lists all registered workspaces and their pinned status."""
    summary = dm.get_workspaces_summary()
    lines = ["Registered Workspaces:"]
    for p in summary["pinned"]:
        lines.append(f"[Pin] {p['name']} - {p['path']}")
    for p in summary["recent"]:
        lines.append(f"      {p['name']} - {p['path']}")
    return "\n".join(lines)

if __name__ == "__main__":
    # When running directly, instructions for Claude Desktop
    print("FileCortex MCP Server Placeholder.")
    print("To use with Claude Desktop, add this to your config:")
    print(f"{{ \"mcpServers\": {{ \"file-cortex\": {{ \"command\": \"python\", \"args\": [\"{os.path.abspath(__file__)}\"] }} }} }}")
