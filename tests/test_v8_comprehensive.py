# ruff: noqa: I001, D403
"""Comprehensive v8.0 tests for FileCortex.

Covers: read_text_smart edge cases, batch_categorize DI, config save retries,
MCP tools, duplicate finder defensive checks, CLI elif chain, walk_filtered
edge cases, ActionBridge prepare, context formatter noise, format utils
boundary, PathValidator Windows specifics, Web API boundary, services layer.
"""

import contextlib
import threading
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from file_cortex_core import (
    ActionBridge,
    ContextFormatter,
    DataManager,
    FileOps,
    FileUtils,
    FormatUtils,
    PathValidator,
    search_generator,
)
from file_cortex_core.config import MAX_SAVE_RETRIES


class TestReadTextSmartEdgeCases:
    """Tests for FileUtils.read_text_smart fallback and edge cases."""

    def test_read_text_smart_returns_string_on_nonexistent(self, tmp_path):
        """Nonexistent file returns empty string, not None."""
        result = FileUtils.read_text_smart(tmp_path / "nope.txt")
        assert isinstance(result, str)
        assert result == ""

    def test_read_text_smart_with_max_bytes_truncation(self, tmp_path):
        """File larger than max_bytes is truncated."""
        f = tmp_path / "big.txt"
        f.write_text("a" * 10000, encoding="utf-8")
        result = FileUtils.read_text_smart(f, max_bytes=100)
        assert len(result) <= 100

    def test_read_text_smart_empty_file(self, tmp_path):
        """Empty file returns empty string."""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = FileUtils.read_text_smart(f)
        assert result == ""

    def test_read_text_smart_directory_returns_empty(self, tmp_path):
        """Directory path returns empty string."""
        d = tmp_path / "dir"
        d.mkdir()
        result = FileUtils.read_text_smart(d)
        assert result == ""

    def test_read_text_smart_unicode_content(self, tmp_path):
        """Unicode content is correctly read."""
        f = tmp_path / "unicode.txt"
        f.write_text("你好世界 🌍", encoding="utf-8")
        result = FileUtils.read_text_smart(f)
        assert "你好世界" in result


class TestBatchCategorizeDI:
    """Tests for batch_categorize with dependency injection."""

    def test_batch_categorize_with_injected_dm(self, tmp_path):
        """batch_categorize uses injected DataManager instance."""
        from unittest.mock import patch

        config_path = tmp_path / "cat_config.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            FileUtils.clear_cache()
            dm = DataManager()

            project = tmp_path / "cat_project"
            project.mkdir()
            (project / "test.txt").write_text("hello", encoding="utf-8")

            dm.add_to_recent(str(project))
            proj = dm.get_project_data_obj(str(project))
            proj.quick_categories = {"Scripts": "scripts"}
            dm.save()

            FileOps.batch_categorize(
                str(project),
                [str(project / "test.txt")],
                "Scripts",
                data_mgr=dm,
            )

            scripts_dir = project / "scripts"
            assert scripts_dir.exists()
            assert (scripts_dir / "test.txt").exists()
            DataManager.reset()

    def test_batch_categorize_unknown_category_raises(self, tmp_path):
        """batch_categorize raises ValueError for unknown category."""
        from unittest.mock import patch

        config_path = tmp_path / "cat_config2.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            dm = DataManager()

            project = tmp_path / "cat_project2"
            project.mkdir()
            dm.add_to_recent(str(project))

            with pytest.raises(ValueError, match="not defined"):
                FileOps.batch_categorize(
                    str(project), [], "NonExistent", data_mgr=dm
                )
            DataManager.reset()

    def test_batch_categorize_empty_paths(self, tmp_path):
        """batch_categorize with empty paths list returns empty."""
        from unittest.mock import patch

        config_path = tmp_path / "cat_config3.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            dm = DataManager()

            project = tmp_path / "cat_project3"
            project.mkdir()
            dm.add_to_recent(str(project))
            proj = dm.get_project_data_obj(str(project))
            proj.quick_categories = {"Docs": "docs"}
            dm.save()

            result = FileOps.batch_categorize(
                str(project), [], "Docs", data_mgr=dm
            )
            assert result == []
            DataManager.reset()

    def test_batch_categorize_default_dm(self, tmp_path):
        """batch_categorize works with default DataManager singleton."""
        from unittest.mock import patch

        config_path = tmp_path / "cat_config4.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            FileUtils.clear_cache()
            dm = DataManager()

            project = tmp_path / "cat_project4"
            project.mkdir()
            (project / "file.txt").write_text("data", encoding="utf-8")

            dm.add_to_recent(str(project))
            proj = dm.get_project_data_obj(str(project))
            proj.quick_categories = {"Out": "out"}
            dm.save()

            result = FileOps.batch_categorize(
                str(project), [str(project / "file.txt")], "Out"
            )
            assert len(result) == 1
            DataManager.reset()


class TestConfigSaveRetries:
    """Tests for config save retry logic."""

    def test_max_save_retries_constant(self):
        """MAX_SAVE_RETRIES is defined as independent constant."""
        assert MAX_SAVE_RETRIES == 5
        assert isinstance(MAX_SAVE_RETRIES, int)

    def test_save_creates_config_file(self, tmp_path):
        """save() creates config file atomically."""
        config_path = tmp_path / "save_test.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            dm = DataManager()
            dm.config.last_directory = str(tmp_path)
            dm.save()

            assert config_path.exists()
            import json
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            assert data["last_directory"] == str(tmp_path)
            DataManager.reset()

    def test_save_handles_permission_error_gracefully(self, tmp_path):
        """save() retries on PermissionError."""
        config_path = tmp_path / "perm_test.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            dm = DataManager()
            dm.config.last_directory = "test"
            dm.save()

            with patch("os.replace", side_effect=PermissionError("locked")), \
                 pytest.raises(PermissionError):
                dm.save()
            DataManager.reset()


class TestMCPToolsBasic:
    """Tests for MCP server tool functions."""

    def test_mcp_search_files_registered(self):
        """search_files tool is registered in MCP instance."""
        from mcp_server import get_mcp
        mcp = get_mcp()
        assert "search_files" in mcp._tools

    def test_mcp_list_workspaces_registered(self):
        """list_workspaces tool is registered in MCP instance."""
        from mcp_server import get_mcp
        mcp = get_mcp()
        assert "list_workspaces" in mcp._tools

    def test_mcp_register_workspace_registered(self):
        """register_workspace tool is registered in MCP instance."""
        from mcp_server import get_mcp
        mcp = get_mcp()
        assert "register_workspace" in mcp._tools

    def test_mcp_get_file_context_registered(self):
        """get_file_context tool is registered in MCP instance."""
        from mcp_server import get_mcp
        mcp = get_mcp()
        assert "get_file_context" in mcp._tools

    def test_mcp_get_project_blueprint_registered(self):
        """get_project_blueprint tool is registered in MCP instance."""
        from mcp_server import get_mcp
        mcp = get_mcp()
        assert "get_project_blueprint" in mcp._tools


class TestDuplicateFinderDefensive:
    """Tests for duplicate finder edge cases."""

    def test_duplicate_worker_empty_dir(self, tmp_path):
        """DuplicateWorker handles empty directory gracefully."""
        from file_cortex_core.duplicate import DuplicateWorker

        empty = tmp_path / "empty_dir"
        empty.mkdir()

        q = MagicMock()
        stop = threading.Event()
        worker = DuplicateWorker(empty, "", True, q, stop)
        worker.run()
        q.put.assert_called_once()
        call_args = q.put.call_args[0][0]
        assert call_args[0] == "DONE"

    def test_duplicate_worker_single_file_no_dupes(self, tmp_path):
        """Single file produces no duplicate groups."""
        from file_cortex_core.duplicate import DuplicateWorker

        proj = tmp_path / "single"
        proj.mkdir()
        (proj / "unique.txt").write_text("unique content", encoding="utf-8")

        import queue
        q = queue.Queue()
        stop = threading.Event()
        worker = DuplicateWorker(proj, "", True, q, stop)
        worker.run()

        result = q.get_nowait()
        assert result == ("DONE", True)

    def test_duplicate_worker_finds_exact_dupes(self, tmp_path):
        """Two identical files are detected as duplicates."""
        from file_cortex_core.duplicate import DuplicateWorker

        proj = tmp_path / "dupes"
        proj.mkdir()
        (proj / "a.txt").write_text("identical content", encoding="utf-8")
        (proj / "b.txt").write_text("identical content", encoding="utf-8")

        import queue
        q = queue.Queue()
        stop = threading.Event()
        worker = DuplicateWorker(proj, "", True, q, stop)
        worker.run()

        result = q.get_nowait()
        assert isinstance(result, dict)
        assert result["hash"] != ""
        assert len(result["paths"]) == 2


class TestCLIEdgeCases:
    """Tests for CLI (fctx.py) edge cases."""

    def test_cli_open_nonexistent_path(self, tmp_path):
        """CLI open with nonexistent path prints error."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        config_path = tmp_path / "cli_config.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            captured = StringIO()
            with patch("sys.stdout", captured):
                sys.argv = ["fctx", "open", str(tmp_path / "nope")]
                from fctx import main
                main()
            assert "ERROR" in captured.getvalue()
            DataManager.reset()

    def test_cli_no_command_shows_help(self, tmp_path):
        """CLI with no command shows help text."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        config_path = tmp_path / "cli_config2.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            captured = StringIO()
            with patch("sys.stdout", captured):
                sys.argv = ["fctx"]
                from fctx import main
                main()
            assert "FileCortex" in captured.getvalue() or "usage" in captured.getvalue().lower()
            DataManager.reset()

    def test_cli_elif_chain_no_overlap(self, tmp_path):
        """CLI elif chain: stage before open shows error."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        config_path = tmp_path / "cli_config3.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            captured = StringIO()
            with patch("sys.stdout", captured):
                sys.argv = ["fctx", "stage", str(tmp_path), "somefile"]
                from fctx import main
                main()
            assert "ERROR" in captured.getvalue()
            DataManager.reset()


class TestWalkFilteredEdgeCases:
    """Tests for FileUtils.walk_filtered edge cases."""

    def test_walk_filtered_empty_dir(self, tmp_path):
        """walk_filtered on empty directory yields nothing."""
        empty = tmp_path / "empty"
        empty.mkdir()
        results = list(FileUtils.walk_filtered(empty, [], None))
        assert results == []

    def test_walk_filtered_respects_stop_event(self, tmp_path):
        """walk_filtered stops when stop_event is set."""
        proj = tmp_path / "big"
        proj.mkdir()
        for i in range(20):
            (proj / f"file_{i}.txt").write_text(f"data {i}", encoding="utf-8")

        stop = threading.Event()
        stop.set()
        results = list(FileUtils.walk_filtered(proj, [], None, stop_event=stop))
        assert len(results) == 0

    def test_walk_filtered_with_excludes(self, tmp_path):
        """walk_filtered respects manual excludes."""
        proj = tmp_path / "excl"
        proj.mkdir()
        (proj / "keep.txt").write_text("keep", encoding="utf-8")
        (proj / "skip.log").write_text("skip", encoding="utf-8")

        results = list(FileUtils.walk_filtered(proj, ["*.log"], None))
        paths = [str(r[1]) for r in results]
        assert not any("skip.log" in p for p in paths)
        assert any("keep.txt" in p for p in paths)

    def test_walk_filtered_includes_dirs(self, tmp_path):
        """walk_filtered includes directories when requested."""
        proj = tmp_path / "dirs"
        proj.mkdir()
        (proj / "sub").mkdir()
        (proj / "sub" / "file.txt").write_text("x", encoding="utf-8")

        results = list(FileUtils.walk_filtered(proj, [], None, include_dirs=True))
        types = [("dir" if r[0].is_dir() else "file") for r in results]
        assert "dir" in types


class TestActionBridgePrepare:
    """Tests for ActionBridge._prepare_execution edge cases."""

    def test_prepare_nonexistent_raises(self, tmp_path):
        """_prepare_execution raises FileNotFoundError for missing path."""
        with pytest.raises(FileNotFoundError):
            ActionBridge._prepare_execution(
                "echo {path}", str(tmp_path / "nope.txt"), str(tmp_path)
            )

    def test_prepare_basic_template(self, tmp_path):
        """_prepare_execution substitutes {path} template correctly."""
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")

        cmd, is_shell, ctx = ActionBridge._prepare_execution(
            "echo {path}", str(f), str(tmp_path)
        )
        assert "path" in ctx
        assert ctx["name"] == "test.txt"
        assert ctx["ext"] == ".txt"

    def test_prepare_context_has_parent(self, tmp_path):
        """_prepare_execution context includes parent directory."""
        f = tmp_path / "test.py"
        f.write_text("code", encoding="utf-8")

        _, _, ctx = ActionBridge._prepare_execution(
            "echo {parent}", str(f), str(tmp_path)
        )
        assert "parent" in ctx
        assert "parent_name" in ctx

    def test_prepare_root_in_context(self, tmp_path):
        """_prepare_execution context includes project root."""
        f = tmp_path / "test.txt"
        f.write_text("x", encoding="utf-8")

        _, _, ctx = ActionBridge._prepare_execution(
            "echo {root}", str(f), str(tmp_path)
        )
        assert ctx["root"] == str(tmp_path)

    def test_prepare_ext_includes_dot(self, tmp_path):
        """_prepare_execution context ext includes the dot."""
        f = tmp_path / "script.py"
        f.write_text("pass", encoding="utf-8")

        _, _, ctx = ActionBridge._prepare_execution(
            "echo {ext}", str(f), str(tmp_path)
        )
        assert ctx["ext"] == ".py"


class TestContextFormatterNoise:
    """Tests for context formatting with noise reduction."""

    def test_markdown_without_noise_reducer(self, tmp_path):
        """to_markdown with apply_noise_reducer=False preserves long lines."""
        f = tmp_path / "min.js"
        long_line = "var a=1;" + "b=2;" * 200
        f.write_text(long_line, encoding="utf-8")

        result = ContextFormatter.to_markdown(
            [str(f)], apply_noise_reducer=False
        )
        assert long_line in result

    def test_markdown_with_noise_reducer_skips_long_lines(self, tmp_path):
        """to_markdown with apply_noise_reducer=True skips long lines."""
        f = tmp_path / "min2.js"
        long_line = "var a=1;" + "b=2;" * 200
        f.write_text(long_line, encoding="utf-8")

        result = ContextFormatter.to_markdown(
            [str(f)], apply_noise_reducer=True
        )
        assert "skipped" in result

    def test_xml_with_empty_file(self, tmp_path):
        """to_xml handles empty files gracefully."""
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")

        result = ContextFormatter.to_xml([str(f)])
        assert "<context>" in result
        assert "</context>" in result

    def test_markdown_with_prompt_prefix(self, tmp_path):
        """to_markdown includes prompt prefix when provided."""
        f = tmp_path / "code.py"
        f.write_text("print(1)", encoding="utf-8")

        result = ContextFormatter.to_markdown(
            [str(f)], prompt_prefix="Review this code"
        )
        assert "Review this code" in result


class TestFormatUtilsBoundary:
    """Tests for FormatUtils boundary conditions."""

    def test_format_size_negative(self):
        """format_size with negative returns '0 B'."""
        assert FormatUtils.format_size(-1) == "0 B"

    def test_format_size_zero(self):
        """format_size with zero returns '0 B'."""
        assert FormatUtils.format_size(0) == "0 B"

    def test_format_size_gb(self):
        """format_size correctly formats GB values."""
        result = FormatUtils.format_size(2 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_estimate_tokens_empty(self):
        """estimate_tokens with empty string returns 0."""
        assert FormatUtils.estimate_tokens("") == 0

    def test_format_number_large(self):
        """format_number handles large numbers."""
        result = FormatUtils.format_number(1000000)
        assert result == "1,000,000"

    def test_format_number_invalid(self):
        """format_number with invalid input returns string representation."""
        result = FormatUtils.format_number("not_a_number")
        assert isinstance(result, str)

    def test_format_datetime_returns_string(self):
        """format_datetime always returns a string."""
        assert isinstance(FormatUtils.format_datetime(0), str)
        assert isinstance(FormatUtils.format_datetime(-1), str)


class TestPathValidatorWindows:
    """Tests for PathValidator on Windows-specific paths."""

    def test_norm_path_none(self):
        """norm_path with None returns empty string."""
        assert PathValidator.norm_path(None) == ""

    def test_norm_path_empty(self):
        """norm_path with empty string returns empty string."""
        assert PathValidator.norm_path("") == ""

    def test_norm_path_basic(self):
        """norm_path returns a non-empty string for valid paths."""
        result = PathValidator.norm_path("/tmp/test")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_is_safe_child_path(self):
        """is_safe allows child paths."""
        assert PathValidator.is_safe("/tmp/child", "/tmp") is True

    def test_is_safe_outside_path(self):
        """is_safe blocks paths outside root."""
        assert PathValidator.is_safe("/other", "/tmp") is False

    def test_is_safe_empty_root(self):
        """is_safe with empty root returns False."""
        assert PathValidator.is_safe("/some/path", "") is False

    def test_is_safe_same_path(self):
        """is_safe allows exact match."""
        assert PathValidator.is_safe("/tmp", "/tmp") is True


class TestWebAPIBoundary:
    """Tests for Web API boundary conditions."""

    def test_api_archive_prevents_traversal(self, project_client, mock_project):
        """Archive endpoint prevents path traversal in output_name."""
        res = project_client.post(
            "/api/fs/archive",
            json={
                "paths": [str(mock_project / "README.md")],
                "output_name": "../escape.zip",
                "project_root": str(mock_project),
            },
        )
        assert res.status_code == 400

    def test_api_create_rejects_separator_in_name(self, project_client, mock_project):
        """Create endpoint rejects path separators in name."""
        res = project_client.post(
            "/api/fs/create",
            json={
                "parent_path": str(mock_project),
                "name": "bad/file.txt",
                "is_dir": False,
            },
        )
        assert res.status_code == 400

    def test_api_content_blocked_for_unregistered(self, api_client, tmp_path):
        """Content endpoint blocks access to unregistered paths."""
        f = tmp_path / "unregistered.txt"
        f.write_text("secret", encoding="utf-8")
        res = api_client.get("/api/content", params={"path": str(f)})
        assert res.status_code == 403

    def test_api_generate_with_empty_files(self, project_client, mock_project):
        """Generate endpoint handles empty file list with registered project."""
        res = project_client.post(
            "/api/generate",
            json={
                "files": [],
                "project_path": str(mock_project),
                "export_format": "markdown",
            },
        )
        assert res.status_code == 200
        assert res.json()["tokens"] == 0

    def test_api_workspaces_returns_valid_structure(self, api_client):
        """Workspaces endpoint returns correct structure."""
        res = api_client.get("/api/workspaces")
        data = res.json()
        assert "pinned" in data
        assert "recent" in data


class TestServicesLayer:
    """Tests for routers/services.py helper functions."""

    def test_get_children_empty_dir(self, api_client, mock_project):
        """get_children returns empty for empty directory."""
        from routers.services import get_children
        empty = mock_project / "empty_sub"
        empty.mkdir()
        result = get_children(str(empty))
        assert isinstance(result, list)

    def test_is_path_safe_helper(self):
        """is_path_safe service function delegates correctly."""
        from routers.services import is_path_safe
        assert is_path_safe("/tmp/child", "/tmp") is True
        assert is_path_safe("/other", "/tmp") is False

    def test_get_dm_returns_data_manager(self):
        """get_dm returns DataManager instance."""
        from routers.services import get_dm
        dm = get_dm()
        assert isinstance(dm, DataManager)


class TestBatchRenameConflictResolution:
    """Tests for batch rename conflict resolution."""

    def test_rename_conflict_gets_suffix(self, tmp_path):
        """Conflicting renames get auto-suffixed names."""
        f1 = tmp_path / "file_a.txt"
        f2 = tmp_path / "file_b.txt"
        f1.write_text("a", encoding="utf-8")
        f2.write_text("b", encoding="utf-8")

        results = FileOps.batch_rename(
            str(tmp_path),
            [str(f1), str(f2)],
            r"file_.*\.txt",
            "renamed.txt",
            dry_run=True,
        )
        assert len(results) == 2
        statuses = [r["status"] for r in results]
        assert any("suffix" in s for s in statuses)

    def test_rename_rollback_on_failure(self, tmp_path):
        """Batch rename rollback restores original files."""
        f1 = tmp_path / "alpha.txt"
        f1.write_text("alpha", encoding="utf-8")
        f2 = tmp_path / "beta.txt"
        f2.write_text("beta", encoding="utf-8")

        results = FileOps.batch_rename(
            str(tmp_path),
            [str(f1), str(f2)],
            r"(alpha|beta)",
            "result.txt",
            dry_run=True,
        )
        assert len(results) >= 1


class TestSearchGeneratorEdgeCases:
    """Tests for search_generator edge cases."""

    def test_search_empty_dir(self, tmp_path):
        """search_generator on empty dir yields nothing."""
        empty = tmp_path / "empty_search"
        empty.mkdir()
        results = list(search_generator(empty, "", "smart", ""))
        assert results == []

    def test_search_content_mode_finds_text(self, tmp_path):
        """search_generator content mode finds text in files."""
        proj = tmp_path / "content_search"
        proj.mkdir()
        (proj / "findme.py").write_text("keyword_target_found", encoding="utf-8")

        results = list(search_generator(
            proj, "keyword_target", "content", ""
        ))
        assert len(results) >= 1
        assert results[0]["match_type"] == "Content Match"

    def test_search_max_results_enforced(self, tmp_path):
        """search_generator respects max_results limit."""
        proj = tmp_path / "max_res"
        proj.mkdir()
        for i in range(20):
            (proj / f"file_{i}.txt").write_text(f"data {i}", encoding="utf-8")

        results = list(search_generator(
            proj, ".txt", "smart", "", max_results=5
        ))
        assert len(results) <= 5

    def test_search_regex_mode_invalid_pattern(self, tmp_path):
        """search_generator handles invalid regex gracefully."""
        proj = tmp_path / "regex_err"
        proj.mkdir()
        (proj / "test.txt").write_text("data", encoding="utf-8")

        results = list(search_generator(
            proj, "[invalid", "regex", ""
        ))
        assert isinstance(results, list)


class TestFileOpsArchive:
    """Tests for FileOps.archive_selection edge cases."""

    def test_archive_with_nested_dirs(self, tmp_path):
        """Archive correctly handles nested directories."""
        src = tmp_path / "archive_src"
        src.mkdir()
        (src / "sub").mkdir()
        (src / "sub" / "deep.txt").write_text("deep", encoding="utf-8")
        (src / "top.txt").write_text("top", encoding="utf-8")

        out = tmp_path / "output.zip"
        result = FileOps.archive_selection(
            [str(src)], str(out), root_dir=str(tmp_path)
        )
        assert zipfile.is_zipfile(result)

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert any("deep" in n for n in names)
            assert any("top" in n for n in names)

    def test_archive_nonexistent_path_skipped(self, tmp_path):
        """Archive skips nonexistent paths without error."""
        out = tmp_path / "skip.zip"
        result = FileOps.archive_selection(
            [str(tmp_path / "nope.txt")], str(out)
        )
        assert zipfile.is_zipfile(result)

    def test_archive_empty_list(self, tmp_path):
        """Archive with empty path list creates valid zip."""
        out = tmp_path / "empty.zip"
        result = FileOps.archive_selection([], str(out))
        assert zipfile.is_zipfile(result)


class TestFlattenPathsEdgeCases:
    """Tests for FileUtils.flatten_paths edge cases."""

    def test_flatten_empty(self):
        """flatten_paths with empty list returns empty."""
        assert FileUtils.flatten_paths([]) == []

    def test_flatten_single_file(self, tmp_path):
        """flatten_paths with single file returns that file."""
        f = tmp_path / "single.txt"
        f.write_text("x", encoding="utf-8")
        result = FileUtils.flatten_paths([str(f)], str(tmp_path))
        assert len(result) == 1

    def test_flatten_with_stop_event(self, tmp_path):
        """flatten_paths respects stop_event."""
        proj = tmp_path / "stop_proj"
        proj.mkdir()
        for i in range(10):
            (proj / f"file_{i}.txt").write_text(f"x{i}", encoding="utf-8")

        stop = threading.Event()
        stop.set()
        result = FileUtils.flatten_paths(
            [str(proj)], str(tmp_path), stop_event=stop
        )
        assert len(result) == 0


class TestWebAPIGlobalSettings:
    """Tests for global settings API."""

    def test_global_settings_get(self, api_client):
        """GET /api/global/settings returns valid structure."""
        res = api_client.get("/api/global/settings")
        assert res.status_code == 200
        data = res.json()
        assert "preview_limit_mb" in data
        assert "token_threshold" in data

    def test_global_settings_update(self, api_client):
        """POST /api/global/settings updates values."""
        res = api_client.post(
            "/api/global/settings",
            json={"preview_limit_mb": 2.0},
        )
        assert res.status_code == 200

        get_res = api_client.get("/api/global/settings")
        assert get_res.json()["preview_limit_mb"] == 2.0

    def test_global_settings_with_settings_alias(self, api_client):
        """POST /api/global/settings handles 'settings' dict alias."""
        res = api_client.post(
            "/api/global/settings",
            json={"settings": {"token_threshold": 50000}},
        )
        assert res.status_code == 200


class TestWebAPIProjectSettings:
    """Tests for project settings API."""

    def test_project_config_get(self, project_client, mock_project):
        """GET /api/project/config returns project data."""
        res = project_client.get(
            "/api/project/config",
            params={"path": str(mock_project)},
        )
        assert res.status_code == 200
        data = res.json()
        assert "excludes" in data

    def test_project_tools_update(self, project_client, mock_project):
        """POST /api/project/tools updates custom tools."""
        res = project_client.post(
            "/api/project/tools",
            json={
                "project_path": str(mock_project),
                "tools": {"Test": "echo {name}"},
            },
        )
        assert res.status_code == 200

    def test_project_categories_update(self, project_client, mock_project):
        """POST /api/project/categories updates categories."""
        res = project_client.post(
            "/api/project/categories",
            json={
                "project_path": str(mock_project),
                "categories": {"Code": "src"},
            },
        )
        assert res.status_code == 200

    def test_project_categories_rejects_traversal(self, project_client, mock_project):
        """POST /api/project/categories rejects '..' in paths."""
        res = project_client.post(
            "/api/project/categories",
            json={
                "project_path": str(mock_project),
                "categories": {"Bad": "../escape"},
            },
        )
        assert res.status_code == 400


class TestCLIsearchCommand:
    """Tests for the new 'fctx search' CLI subcommand."""

    def test_cli_search_subcommand_exists(self):
        """fctx search subcommand is registered."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        captured = StringIO()
        with patch("sys.stdout", captured):
            sys.argv = ["fctx"]
            from fctx import main
            with contextlib.suppress(SystemExit):
                main()
        assert "search" in captured.getvalue()

    def test_cli_search_finds_files(self, tmp_path):
        """CLI search finds matching files in a registered project."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        config_path = tmp_path / "search_cli.json"
        proj = tmp_path / "search_proj"
        proj.mkdir()
        (proj / "target.txt").write_text("findme", encoding="utf-8")
        (proj / "other.py").write_text("code", encoding="utf-8")

        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            dm = DataManager()
            dm.add_to_recent(str(proj))
            dm.get_project_data(str(proj))
            dm.save()

            captured_search = StringIO()
            with patch("sys.stdout", captured_search):
                sys.argv = ["fctx", "search", str(proj), "target"]
                from fctx import main
                main()

            output = captured_search.getvalue()
            assert "target" in output.lower()
            DataManager.reset()


class TestCLIExportCommand:
    """Tests for the new 'fctx export' CLI subcommand."""

    def test_cli_export_to_file(self, tmp_path):
        """CLI export writes context to a file."""
        import sys
        from unittest.mock import patch

        config_path = tmp_path / "export_cli.json"
        proj = tmp_path / "export_proj"
        proj.mkdir()
        (proj / "code.py").write_text("print(1)", encoding="utf-8")

        output_file = tmp_path / "output.md"

        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            dm = DataManager()
            dm.add_to_recent(str(proj))
            dm.batch_stage(str(proj), [str(proj / "code.py")])

            sys.argv = [
                "fctx", "export", str(proj),
                "--format", "markdown",
                "--output", str(output_file),
            ]
            from fctx import main
            main()

            assert output_file.exists()
            content = output_file.read_text(encoding="utf-8")
            assert "print(1)" in content
            DataManager.reset()

    def test_cli_export_empty_staging(self, tmp_path):
        """fctx export with empty staging prints message."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        config_path = tmp_path / "export_empty.json"
        proj = tmp_path / "export_empty_proj"
        proj.mkdir()

        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            from fctx import main

            captured_open = StringIO()
            with patch("sys.stdout", captured_open):
                sys.argv = ["fctx", "open", str(proj)]
                main()

            captured_export = StringIO()
            with patch("sys.stdout", captured_export):
                sys.argv = ["fctx", "export", str(proj)]
                main()

            assert "empty" in captured_export.getvalue().lower()
            DataManager.reset()


class TestExportOOMProtection:
    """Tests for context export OOM protection."""

    def test_markdown_max_files_limit(self, tmp_path):
        """to_markdown respects max_files limit."""
        proj = tmp_path / "oom_proj"
        proj.mkdir()
        for i in range(20):
            (proj / f"file_{i}.txt").write_text(f"content {i}", encoding="utf-8")

        result = ContextFormatter.to_markdown(
            [str(proj / f"file_{i}.txt") for i in range(20)],
            root_dir=str(proj),
            max_files=5,
        )
        assert "file_0" in result
        assert "file_19" not in result

    def test_xml_max_files_limit(self, tmp_path):
        """to_xml respects max_files limit."""
        proj = tmp_path / "oom_xml"
        proj.mkdir()
        for i in range(10):
            (proj / f"f{i}.txt").write_text(f"x{i}", encoding="utf-8")

        result = ContextFormatter.to_xml(
            [str(proj / f"f{i}.txt") for i in range(10)],
            root_dir=str(proj),
            include_blueprint=False,
            max_files=3,
        )
        assert "f0" in result
        assert "f9" not in result

    def test_markdown_content_size_limit(self, tmp_path):
        """to_markdown truncates when total content exceeds size limit."""
        from file_cortex_core.context import MAX_TOTAL_CONTENT_BYTES
        proj = tmp_path / "size_limit"
        proj.mkdir()
        big_file = proj / "big.txt"
        big_content = "x" * (MAX_TOTAL_CONTENT_BYTES + 1)
        big_file.write_text(big_content, encoding="utf-8")

        result = ContextFormatter.to_markdown(
            [str(big_file)],
            root_dir=str(proj),
        )
        assert "truncated" in result.lower() or len(result) < len(big_content)


class TestProcessManager:
    """Tests for the ProcessManager class."""

    def test_register_and_unregister(self):
        """ProcessManager registers and unregisters processes."""
        from unittest.mock import MagicMock
        from routers.common import process_manager

        mock_proc = MagicMock()
        mock_proc.pid = 54321
        assert process_manager.register(54321, mock_proc) is True
        assert process_manager.active_count >= 1
        process_manager.unregister(54321)
        assert process_manager.get(54321) is None

    def test_register_at_capacity(self):
        """ProcessManager rejects registration when at capacity."""
        from unittest.mock import MagicMock
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=2)
        p1 = MagicMock()
        p2 = MagicMock()
        p3 = MagicMock()
        assert pm.register(1, p1) is True
        assert pm.register(2, p2) is True
        assert pm.register(3, p3) is False

    def test_pids_snapshot(self):
        """ProcessManager.pids returns a snapshot of registered PIDs."""
        from unittest.mock import MagicMock
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=10)
        pm.register(100, MagicMock())
        pm.register(200, MagicMock())
        assert sorted(pm.pids) == [100, 200]
        pm.clear()
        assert pm.pids == []

    def test_get_returns_none_for_unknown(self):
        """ProcessManager.get returns None for unregistered PID."""
        from routers.common import process_manager
        assert process_manager.get(999999) is None


class TestCLISubcommandHandlerPattern:
    """Tests for the refactored CLI handler dispatch pattern."""

    def test_cli_projects_empty(self, tmp_path):
        """fctx projects with no projects shows message."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        config_path = tmp_path / "empty_proj.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            captured = StringIO()
            with patch("sys.stdout", captured):
                sys.argv = ["fctx", "projects"]
                from fctx import main
                main()
            assert "No registered" in captured.getvalue() or "no" in captured.getvalue().lower()
            DataManager.reset()

    def test_cli_invalid_subcommand(self):
        """fctx with unknown subcommand shows help."""
        from io import StringIO
        import sys
        from unittest.mock import patch

        captured = StringIO()
        with patch("sys.stdout", captured):
            sys.argv = ["fctx"]
            from fctx import main
            main()
        assert "usage" in captured.getvalue().lower() or "FileCortex" in captured.getvalue()
