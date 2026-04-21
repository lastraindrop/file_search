import pytest

import mcp_server
from file_cortex_core import PathValidator


@pytest.mark.asyncio
async def test_mcp_register_workspace_enables_followup_tools(clean_config, mock_project):
    """Registering a workspace should initialize project state for later MCP tools."""
    project_path = str(mock_project)

    result = await mcp_server.register_workspace(project_path, auto_pin=True)
    assert "registered successfully" in result.lower()

    summary = await mcp_server.list_workspaces()
    assert PathValidator.norm_path(project_path) in summary

    search_result = await mcp_server.search_files(project_path, "main", mode="smart")
    assert "main.py" in search_result


@pytest.mark.asyncio
async def test_mcp_get_file_context_xml(clean_config, mock_project):
    """MCP context export should return XML for registered workspaces."""
    project_path = str(mock_project)
    file_path = str(mock_project / "src" / "main.py")

    await mcp_server.register_workspace(project_path)
    result = await mcp_server.get_file_context(project_path, [file_path], format="xml")

    assert "<context>" in result
    assert "main.py" in result


@pytest.mark.asyncio
async def test_mcp_blueprint_and_stats(clean_config, mock_project):
    """Blueprint and stats tools should work once the workspace is registered."""
    project_path = str(mock_project)
    file_path = str(mock_project / "src" / "main.py")

    await mcp_server.register_workspace(project_path)

    blueprint = await mcp_server.get_project_blueprint(project_path, max_depth=2)
    assert "Project:" in blueprint
    assert "src" in blueprint

    stats = await mcp_server.get_file_stats(project_path, [file_path])
    assert "File Statistics:" in stats
    assert "main.py" in stats
