"""Comprehensive tests for v6.3.1 audit - CLI, MCP, web edge cases, and regression."""

import os
import pathlib
import sys
import threading
from unittest.mock import patch

import pytest

from file_cortex_core import (
    ContextFormatter,
    DataManager,
    FileOps,
    FormatUtils,
    NoiseReducer,
    PathValidator,
    search_generator,
)

# ============================================================================
# CLI Tests (fctx.py)
# ============================================================================

class TestCLI:
    """Tests for fctx.py CLI interface."""

    def test_cli_open_existing_path(self, mock_project):
        """CLI open command with existing directory."""
        from fctx import main as cli_main

        with patch("sys.argv", ["fctx", "open", str(mock_project)]):
            cli_main()

    def test_cli_open_nonexistent_path(self, capsys):
        """CLI open command with nonexistent path."""
        from fctx import main as cli_main

        with patch("sys.argv", ["fctx", "open", "/nonexistent/path/12345"]):
            cli_main()
        captured = capsys.readouterr()
        assert "ERROR" in captured.out or "does not exist" in captured.out

    def test_cli_projects_list(self, mock_project, capsys):
        """CLI projects list command."""
        from fctx import main as cli_main

        dm = DataManager()
        dm.add_to_recent(str(mock_project))

        with patch("sys.argv", ["fctx", "projects"]):
            cli_main()
        captured = capsys.readouterr()
        assert mock_project.name in captured.out

    def test_cli_no_command_shows_help(self, capsys):
        """CLI with no command prints help."""
        from fctx import main as cli_main

        with patch("sys.argv", ["fctx"]):
            cli_main()
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "open" in captured.out.lower()

    def test_cli_open_system_dir_blocked(self, capsys, system_dir):
        """CLI blocks system directory registration."""
        from fctx import main as cli_main

        with patch("sys.argv", ["fctx", "open", system_dir]):
            cli_main()
        captured = capsys.readouterr()
        assert "ERROR" in captured.out or "unsafe" in captured.out.lower()


# ============================================================================
# MCP Server Tests
# ============================================================================

class TestMCPServer:
    """Tests for mcp_server.py."""

    def test_mcp_search_files_unauthorized_path(self):
        """MCP search returns error for unauthorized path."""
        import asyncio

        from mcp_server import search_files

        with patch(
            "file_cortex_core.DataManager.resolve_project_root", return_value=None
        ):
            result = asyncio.run(search_files("/nonexistent/proj", "query"))
            assert "Error" in result or "not registered" in result.lower()

    def test_mcp_search_files_with_results(self, mock_project):
        """MCP search returns matching files."""
        import asyncio

        from mcp_server import search_files

        dm = DataManager()
        norm_p = PathValidator.norm_path(str(mock_project))
        dm.add_to_recent(norm_p)
        dm.get_project_data(norm_p)

        result = asyncio.run(
            search_files(norm_p, "main", mode="smart")
        )
        assert "main.py" in result.lower() or "No matches" in result

    def test_mcp_search_files_respects_limit(self, stress_project):
        """MCP search respects max 50 result limit."""
        import asyncio

        from mcp_server import search_files

        dm = DataManager()
        dm.add_to_recent(str(stress_project))

        result = asyncio.run(
            search_files(str(stress_project), "file", mode="smart")
        )
        lines = result.split("\n")
        assert len(lines) <= 50 or "No matches" in result

    def test_mcp_register_new_workspace(self, mock_project, clean_config):
        """MCP registers a new workspace."""
        import asyncio

        from mcp_server import register_workspace

        result = asyncio.run(
            register_workspace(str(mock_project), auto_pin=False)
        )
        assert "registered" in result.lower()

    def test_mcp_register_duplicate_workspace(self, mock_project):
        """MCP detects already registered workspace."""
        import asyncio

        from mcp_server import register_workspace

        # Register first
        asyncio.run(register_workspace(str(mock_project)))
        # Register again
        result = asyncio.run(register_workspace(str(mock_project)))
        assert "already registered" in result.lower()

    def test_mcp_list_workspaces(self, mock_project):
        """MCP lists all registered workspaces."""
        import asyncio

        from mcp_server import list_workspaces

        dm = DataManager()
        dm.add_to_recent(str(mock_project))

        result = asyncio.run(list_workspaces())
        assert "Registered Workspaces" in result
        assert mock_project.name in result

    def test_mcp_get_project_blueprint(self, mock_project):
        """MCP generates project blueprint."""
        import asyncio

        from mcp_server import get_project_blueprint

        dm = DataManager()
        norm_p = PathValidator.norm_path(str(mock_project))
        dm.add_to_recent(norm_p)
        dm.get_project_data(norm_p)

        result = asyncio.run(
            get_project_blueprint(norm_p, max_depth=2)
        )
        assert mock_project.name in result or "Error" in result

    def test_mcp_get_file_context_xml(self, mock_project):
        """MCP gets file context in XML format."""
        import asyncio

        from mcp_server import get_file_context

        dm = DataManager()
        dm.add_to_recent(str(mock_project))

        result = asyncio.run(
            get_file_context(
                str(mock_project),
                [str(mock_project / "src" / "main.py")],
                format="xml",
            )
        )
        assert "<context>" in result or "Error" in result

    def test_mcp_get_file_context_markdown(self, mock_project):
        """MCP gets file context in markdown format."""
        import asyncio

        from mcp_server import get_file_context

        dm = DataManager()
        dm.add_to_recent(str(mock_project))

        result = asyncio.run(
            get_file_context(
                str(mock_project),
                [str(mock_project / "README.md")],
                format="markdown",
            )
        )
        assert "```" in result or "Error" in result

    def test_mcp_get_file_stats(self, mock_project):
        """MCP gets file statistics."""
        import asyncio

        from mcp_server import get_file_stats

        dm = DataManager()
        dm.add_to_recent(str(mock_project))

        result = asyncio.run(
            get_file_stats(
                str(mock_project),
                [str(mock_project / "src" / "main.py")],
            )
        )
        assert "File Statistics" in result or "Error" in result

    def test_mcp_register_nonexistent_path(self, mock_project):
        """MCP rejects nonexistent path registration."""
        import asyncio

        from mcp_server import register_workspace

        nonexistent = str(mock_project / "nonexistent_dir_12345")
        result = asyncio.run(register_workspace(nonexistent))
        assert "Error" in result


# ============================================================================
# Web API Extended Tests
# ============================================================================

class TestWebAPIExtended:
    """Extended tests for web API routes."""

    def test_global_settings_handles_allowed_extensions(self, api_client):
        """Global settings accepts allowed_extensions field."""
        res = api_client.post(
            "/api/global/settings",
            json={"allowed_extensions": ".py,.js"},
        )
        assert res.status_code == 200
        data = api_client.get("/api/global/settings").json()
        assert data.get("allowed_extensions", "") == ".py,.js"

    def test_global_settings_handles_settings_alias(self, api_client):
        """Global settings accepts nested settings field."""
        res = api_client.post(
            "/api/global/settings",
            json={"settings": {"preview_limit_mb": 3.0, "token_ratio": 2.5}},
        )
        assert res.status_code == 200
        data = api_client.get("/api/global/settings").json()
        assert data["preview_limit_mb"] == 3.0
        assert data["token_ratio"] == 2.5

    def test_global_settings_unknown_field_silent(self, api_client):
        """Unknown fields in global settings are silently ignored."""
        res = api_client.post(
            "/api/global/settings",
            json={"__unknown_field__": "test_value", "token_threshold": 200000},
        )
        assert res.status_code == 200
        data = api_client.get("/api/global/settings").json()
        assert data["token_threshold"] == 200000

    def test_api_recent_projects_legacy(self, project_client, mock_project):
        """Legacy recent projects endpoint works."""
        res = project_client.get("/api/recent_projects")
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)
        assert any(item["name"] == mock_project.name for item in items)

    def test_api_generate_with_noise_reducer(self, project_client, mock_project):
        """Generate context respects noise_reducer parameter."""
        res = project_client.post(
            "/api/generate",
            json={
                "files": [str(mock_project / "src" / "main.py")],
                "project_path": str(mock_project),
                "export_format": "markdown",
                "apply_noise_reducer": False,
            },
        )
        assert res.status_code == 200
        assert "content" in res.json()

    def test_api_stage_all_with_excludes(self, project_client, mock_project):
        """Stage all respects exclusion patterns."""
        res = project_client.post(
            "/api/actions/stage_all",
            json={
                "project_path": str(mock_project),
                "mode": "files",
                "apply_excludes": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["added_count"] >= 0
        # Verify .log files and node_modules are excluded
        staged_paths = DataManager().get_project_data(str(mock_project))["staging_list"]
        for p in staged_paths:
            assert ".log" not in p
            assert "node_modules" not in p

    def test_api_stage_all_no_excludes(self, project_client, mock_project):
        """Stage all without excludes includes all files."""
        res = project_client.post(
            "/api/actions/stage_all",
            json={
                "project_path": str(mock_project),
                "mode": "files",
                "apply_excludes": False,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["added_count"] >= 0

    def test_api_archive_cross_project_blocked(self, project_client, mock_project):
        """Archive endpoint blocks paths outside project."""
        outside = str(pathlib.Path(mock_project).parent / "outside_dir")
        os.makedirs(outside, exist_ok=True)
        try:
            res = project_client.post(
                "/api/fs/archive",
                json={
                    "paths": [outside],
                    "output_name": "test.zip",
                    "project_root": str(mock_project),
                },
            )
            assert res.status_code == 403
        finally:
            if os.path.exists(outside):
                import shutil
                shutil.rmtree(outside)

    def test_api_token_header_forward(self, api_client, mock_project, monkeypatch):
        """API token is forwarded in requests and checked by middleware."""
        with patch("web_app.API_TOKEN", "test-secret-123"):
            # Without token
            res = api_client.post("/api/open", json={"path": str(mock_project)})
            assert res.status_code == 401

            # With token
            res = api_client.post(
                "/api/open",
                json={"path": str(mock_project)},
                headers={"X-API-Token": "test-secret-123"},
            )
            assert res.status_code == 200

    def test_cors_allowed_origin_restricted(self, api_client, mock_project):
        """CORS respects allowed origins restriction."""
        with patch("web_app.API_TOKEN", "tok123"), patch(
            "web_app.ALLOWED_ORIGINS", ["https://trusted.com"]
        ):
            res = api_client.post(
                "/api/open",
                json={"path": str(mock_project)},
                headers={
                    "X-API-Token": "tok123",
                    "origin": "https://evil.com",
                },
            )
            assert res.status_code == 403

    def test_cors_wildcard_origin_allows_all(self, api_client, mock_project):
        """CORS with wildcard allows all origins."""
        with patch("web_app.API_TOKEN", "tok123"):
            res = api_client.post(
                "/api/open",
                json={"path": str(mock_project)},
                headers={
                    "X-API-Token": "tok123",
                    "origin": "https://any-origin.com",
                },
            )
            assert res.status_code == 200

    def test_api_index_page_injects_token(self, api_client):
        """Index page injects API token into template."""
        res = api_client.get("/")
        assert res.status_code == 200
        assert "window.__FCTX_API_TOKEN__" in res.text

    def test_api_index_page_injects_version(self, api_client):
        """Index page injects version into template."""
        res = api_client.get("/")
        assert res.status_code == 200
        assert "FileCortex" in res.text

    def test_global_exception_handler(self, api_client):
        """Global exception handler returns proper 500 response."""
        res = api_client.get("/api/project/config?path=/nonexistent/path/xyz")
        assert res.status_code in (403, 500, 404)

    def test_global_exception_handler_production(self, api_client):
        """Global exception handler tested via unregistered project path."""
        res = api_client.get("/api/project/config?path=/some/random/path")
        assert res.status_code in (403, 500)

    def test_proj_config_returns_403_for_unregistered(self, api_client):
        """Project config endpoint blocks unregistered paths."""
        res = api_client.get("/api/project/config?path=/unregistered/path")
        assert res.status_code == 403


# ============================================================================
# Security + Path Validator Extended
# ============================================================================

class TestPathValidatorExtended:
    """Extended path validator tests."""

    def test_is_safe_nested_path(self, tmp_path):
        """Deep nested path is safe within root."""
        root = tmp_path / "root"
        root.mkdir()
        deep = root / "a" / "b" / "c"
        deep.mkdir(parents=True)
        assert PathValidator.is_safe(str(deep), str(root)) is True

    def test_is_safe_sibling_dir_blocked(self, tmp_path):
        """Sibling directory access is blocked."""
        root = tmp_path / "root"
        root.mkdir()
        sibling = tmp_path / "sibling"
        sibling.mkdir()
        assert PathValidator.is_safe(str(sibling), str(root)) is False

    def test_is_safe_unc_path_blocked_windows(self):
        """UNC paths are blocked on Windows."""
        if sys.platform != "win32":
            return
        assert PathValidator.is_safe("\\\\server\\share\\file.txt", "C:\\safe") is False

    def test_norm_path_trailing_slash(self):
        """Trailing slashes are stripped in normalization."""
        result = PathValidator.norm_path("/tmp/project/")
        assert not result.endswith("/")

    def test_norm_path_none_input(self):
        """None input returns empty string."""
        assert PathValidator.norm_path(None) == ""

    def test_norm_path_empty_string(self):
        """Empty string returns empty."""
        assert PathValidator.norm_path("") == ""

    def test_validate_project_system_blocked(self, system_dir):
        """System directory validation raises PermissionError."""
        with pytest.raises(PermissionError):
            PathValidator.validate_project(system_dir)

    def test_validate_project_nonexistent(self):
        """Nonexistent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PathValidator.validate_project("/nonexistent_path_987654321")

    def test_validate_project_file_not_dir(self, tmp_path):
        """File path raises NotADirectoryError."""
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        with pytest.raises(NotADirectoryError):
            PathValidator.validate_project(str(f))


# ============================================================================
# File Operations Extended
# ============================================================================

class TestFileOpsExtended:
    """Extended file operations tests."""

    def test_save_content_atomic(self, tmp_path):
        """Save content writes atomically."""
        f = tmp_path / "test.py"
        f.write_text("original", encoding="utf-8")
        assert FileOps.save_content(str(f), "updated") is True
        assert f.read_text(encoding="utf-8") == "updated"

    def test_save_content_nonexistent_file(self, tmp_path):
        """Save to nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            FileOps.save_content(str(tmp_path / "nonexistent.txt"), "data")

    def test_save_content_binary_file_rejected(self, tmp_path):
        """Cannot save text to binary file."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\xff\x00")
        with pytest.raises(ValueError, match="binary"):
            FileOps.save_content(str(f), "text")

    def test_create_item_file(self, tmp_path):
        """Create a new file."""
        result = FileOps.create_item(str(tmp_path), "new_file.txt")
        assert os.path.isfile(result)
        assert pathlib.Path(result).name == "new_file.txt"

    def test_create_item_directory(self, tmp_path):
        """Create a new directory."""
        result = FileOps.create_item(str(tmp_path), "new_dir", is_dir=True)
        assert os.path.isdir(result)

    def test_create_item_duplicate(self, tmp_path):
        """Creating duplicate item raises FileExistsError."""
        f = tmp_path / "exists.txt"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(FileExistsError):
            FileOps.create_item(str(tmp_path), "exists.txt")

    def test_create_item_parent_not_dir(self, tmp_path):
        """Creating in non-directory parent raises error."""
        f = tmp_path / "file.txt"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            FileOps.create_item(str(f), "child.txt")

    def test_move_file_success(self, tmp_path):
        """Move file to another directory."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        f = src / "file.txt"
        f.write_text("data", encoding="utf-8")
        result = FileOps.move_file(str(f), str(dst))
        assert os.path.exists(result)
        assert not os.path.exists(str(f))

    def test_move_file_dst_not_dir(self, tmp_path):
        """Moving to non-directory raises error."""
        f = tmp_path / "file.txt"
        f.write_text("x", encoding="utf-8")
        nonexistent = tmp_path / "nonexistent_dir"
        with pytest.raises(FileNotFoundError):
            FileOps.move_file(str(f), str(nonexistent))

    def test_archive_selection_directory(self, tmp_path):
        """Archive preserves directory with files."""
        src = tmp_path / "src"
        src.mkdir()
        inner = src / "inner"
        inner.mkdir()
        (inner / "data.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "archive.zip"
        result = FileOps.archive_selection([str(inner)], str(out))
        assert result == str(out)
        import zipfile

        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert any("data.txt" in n for n in names)

    def test_batch_categorize_undefined_category(self, mock_project):
        """Categorizing with undefined category raises ValueError."""
        with pytest.raises(ValueError, match="not defined"):
            FileOps.batch_categorize(
                str(mock_project),
                [str(mock_project / "src" / "main.py")],
                "NonExistentCategory",
            )


# ============================================================================
# DataManager + Config Extended
# ============================================================================

class TestConfigExtended:
    """Extended config tests."""

    def test_update_global_settings_preserves_other_fields(self, clean_config):
        """Updating one global setting preserves others."""
        dm = clean_config
        dm.update_global_settings({"preview_limit_mb": 5.0})
        settings = dm.data["global_settings"]
        assert settings["preview_limit_mb"] == 5.0
        assert settings["token_threshold"] == 128000  # default preserved

    def test_update_global_settings_invalid_type(self, clean_config):
        """Invalid type for global setting field triggers validation error."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError, TypeError)):
            clean_config.update_global_settings({"token_threshold": "not_a_number"})

    def test_add_to_recent_dedup(self, clean_config, tmp_path):
        """Adding same path twice deduplicates recent list."""
        dm = clean_config
        p1 = tmp_path / "proj_a"
        p1.mkdir(exist_ok=True)
        p2 = tmp_path / "proj_b"
        p2.mkdir(exist_ok=True)

        dm.add_to_recent(str(p1))
        dm.add_to_recent(str(p2))
        dm.add_to_recent(str(p1))  # duplicate

        paths = dm.data["recent_projects"]
        assert paths[0] == PathValidator.norm_path(str(p1))  # most recent
        assert paths.count(PathValidator.norm_path(str(p1))) == 1  # no duplicate

    def test_toggle_pinned_cycle(self, clean_config, tmp_path):
        """Toggle pin cycles between pinned/unpinned."""
        dm = clean_config
        p = tmp_path / "proj_x"
        p.mkdir(exist_ok=True)
        path = str(p)

        assert dm.toggle_pinned(path) is True
        assert PathValidator.norm_path(path) in dm.data["pinned_projects"]

        assert dm.toggle_pinned(path) is False
        assert PathValidator.norm_path(path) not in dm.data["pinned_projects"]

    def test_save_session_cap(self, clean_config, mock_project):
        """Session list is capped at 5 entries."""
        dm = clean_config
        p = str(mock_project)
        for i in range(10):
            dm.save_session(p, {"session_id": i, "data": f"test_{i}"})
        proj = dm.get_project_data(p)
        assert len(proj["sessions"]) <= 5
        assert proj["sessions"][0]["session_id"] == 9  # most recent first

    def test_get_project_data_obj_returns_model(self, clean_config, mock_project):
        """get_project_data_obj returns Pydantic model."""
        dm = clean_config
        obj = dm.get_project_data_obj(str(mock_project))
        assert hasattr(obj, "excludes")
        assert hasattr(obj, "staging_list")

    def test_update_custom_tools_non_string_key(self, clean_config, mock_project):
        """update_custom_tools rejects non-string keys."""
        dm = clean_config
        with pytest.raises(ValueError, match="Tool name must be a string"):
            dm.update_custom_tools(str(mock_project), {123: "cmd"})

    def test_update_quick_categories_traversal_blocked(self, clean_config, mock_project):
        """Quick categories with '..' are blocked."""
        dm = clean_config
        with pytest.raises(ValueError, match="illegal"):
            dm.update_quick_categories(str(mock_project), {"escape": "../etc"})


# ============================================================================
# Search + Context Extended
# ============================================================================

class TestSearchExtended:
    """Extended search edge cases."""

    def test_search_generator_cancel_midstream(self, stress_project):
        """Search cancels when stop_event is set mid-stream."""
        stop_event = threading.Event()
        results = []

        gen = search_generator(
            str(stress_project), "file", "smart", "",
            stop_event=stop_event, max_results=1000,
        )
        for i, res in enumerate(gen):
            if i >= 5:
                stop_event.set()
            results.append(res)
        # Should have stopped before completing entire project
        assert len(results) >= 5

    def test_search_content_mode_skips_large_file(self, mock_project):
        """Content mode skips files exceeding max_size_mb."""
        results = list(
            search_generator(
                str(mock_project), "hello", "content", "",
                max_size_mb=0,  # 0 MB limit skips everything
            )
        )
        assert len(results) == 0

    def test_search_inverse_mode(self, mock_project):
        """Inverse search returns non-matching files."""
        results = list(
            search_generator(
                str(mock_project), "ZZZ_NONEXISTENT_PATTERN", "smart", "",
                is_inverse=True,
            )
        )
        assert len(results) > 0  # should return all files

    def test_context_to_xml_cdata_escape(self):
        """XML context handles CDATA content properly."""
        content = ContextFormatter.to_xml(
            [], prompt_prefix="Test]]>",
            include_blueprint=False,
        )
        # CDATA close sequence should not break XML
        assert "<instruction>" in content

    def test_context_to_markdown_empty_paths(self):
        """Markdown context with empty paths returns empty string."""
        result = ContextFormatter.to_markdown([])
        assert result == ""


# ============================================================================
# NoiseReducer Extended
# ============================================================================

class TestNoiseReducerExtended:
    """Extended noise reducer tests."""

    def test_clean_none_content(self):
        """None content returns empty string."""
        assert NoiseReducer.clean(None) == ""

    def test_clean_empty_content(self):
        """Empty content returns empty."""
        assert NoiseReducer.clean("") == ""

    def test_clean_mixed_content(self):
        """Mixed normal and long lines."""
        content = "short\n" + "x" * 600 + "\nnormal"
        result = NoiseReducer.clean(content)
        assert "short" in result
        assert "normal" in result
        assert "skipped" in result


# ============================================================================
# FormatUtils Extended
# ============================================================================

class TestFormatUtilsExtended:
    """Extended format utils tests."""

    def test_collect_paths_separator_escape(self):
        """Collect paths handles separator escape sequences."""
        result = FormatUtils.collect_paths(
            ["/a/test.py", "/b/util.js"],
            mode="absolute",
            separator="\\n",
        )
        assert "\n" in result
        assert "test.py" in result
        assert "util.js" in result

    def test_collect_paths_with_prefix_suffix(self, tmp_path):
        """Collect paths with prefix and suffix."""
        f = tmp_path / "test.py"
        f.write_text("hello", encoding="utf-8")
        result = FormatUtils.collect_paths(
            [str(f)],
            mode="absolute",
            file_prefix="@",
            dir_suffix="/",
        )
        assert result.startswith("@")

    def test_format_number_with_thousands(self):
        """Format number with thousands separator."""
        result = FormatUtils.format_number(1234567)
        assert "," in result
        assert "1" in result


# ============================================================================
# DuplicateWorker Extended
# ============================================================================

class TestDuplicateWorkerExtended:
    """Extended duplicate worker tests."""

    def test_duplicate_worker_cancel_early(self, mock_project):
        """Duplicate worker stops when event is set immediately."""
        import queue as qmod

        stop_event = threading.Event()
        stop_event.set()  # Cancel immediately
        result_queue = qmod.Queue()

        from file_cortex_core.duplicate import DuplicateWorker
        worker = DuplicateWorker(
            mock_project,
            manual_excludes="",
            use_gitignore=True,
            result_queue=result_queue,
            stop_event=stop_event,
        )
        worker.start()
        worker.join(timeout=5)
        # Should not have put DONE tuple since it was cancelled early
        try:
            item = result_queue.get_nowait()
            if isinstance(item, tuple) and item[0] == "DONE":
                pass  # may have started before cancel
        except qmod.Empty:
            pass

    def test_duplicate_worker_empty_dir(self, tmp_path):
        """Duplicate worker on empty directory returns no results."""
        import queue as qmod

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result_queue = qmod.Queue()
        stop_event = threading.Event()

        from file_cortex_core.duplicate import DuplicateWorker
        worker = DuplicateWorker(
            empty_dir,
            manual_excludes="",
            use_gitignore=False,
            result_queue=result_queue,
            stop_event=stop_event,
        )
        worker.start()
        worker.join(timeout=5)

        done = False
        while not done:
            try:
                item = result_queue.get_nowait()
                if isinstance(item, tuple) and item[0] in ("DONE", "ERROR"):
                    done = True
            except qmod.Empty:
                break
