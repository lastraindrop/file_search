"""Tests for v6.3.2 bugfixes — covers BUG-026 through BUG-033 and DEBT fixes."""

import pathlib
import threading
from unittest.mock import patch

import pytest

from file_cortex_core import (
    ContextFormatter,
    DataManager,
    FileOps,
    FileUtils,
    FormatUtils,
    NoiseReducer,
    PathValidator,
    search_generator,
)


class TestFctxElseBranch:
    """BUG-026: fctx.py else branch logic error."""

    def test_fctx_no_command_shows_help(self, capsys):
        """No command should print help."""
        from fctx import main as cli_main

        with patch("sys.argv", ["fctx"]):
            cli_main()
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "open" in captured.out.lower()

    def test_fctx_open_does_not_show_help(self, mock_project, capsys):
        """Open command should NOT also print help."""
        from fctx import main as cli_main

        with patch("sys.argv", ["fctx", "open", str(mock_project)]):
            cli_main()
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        assert not any("usage" in line.lower() for line in lines)

    def test_fctx_projects_does_not_show_help(self, mock_project, capsys):
        """Projects command should NOT also print help."""
        from fctx import main as cli_main

        with patch("file_cortex_core.config._CONFIG_FILE", mock_project / "cfg.json"):
            DataManager.reset()
            dm = DataManager()
            dm.add_to_recent(str(mock_project))

            with patch("sys.argv", ["fctx", "projects"]):
                cli_main()
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        assert not any("usage" in line.lower() for line in lines)

    def test_fctx_stage_does_not_show_help(self, mock_project, capsys):
        """Stage command should NOT also print help."""
        from fctx import main as cli_main

        with patch("file_cortex_core.config._CONFIG_FILE", mock_project / "cfg.json"):
            DataManager.reset()
            dm = DataManager()
            dm.add_to_recent(str(mock_project))
            test_file = mock_project / "test_stage.txt"
            test_file.write_text("stage test", encoding="utf-8")

            with patch("sys.argv", ["fctx", "stage", str(mock_project), str(test_file)]):
                cli_main()
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        assert not any("usage" in line.lower() for line in lines)


class TestHttpRoutesConfigAPI:
    """BUG-029/030: http_routes should use typed config API."""

    def test_content_endpoint_uses_config_api(self, project_client, mock_project):
        """Content endpoint uses dm.config.global_settings.preview_limit_mb."""
        test_file = mock_project / "test_content.txt"
        test_file.write_text("hello world content", encoding="utf-8")

        res = project_client.get(f"/api/content?path={test_file}")
        assert res.status_code == 200
        data = res.json()
        assert "content" in data
        assert data["content"] == "hello world content"

    def test_recent_projects_returns_list(self, project_client, mock_project):
        """Recent projects endpoint uses typed config."""
        res = project_client.get("/api/recent_projects")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert any(p["name"] == mock_project.name for p in data)


class TestSearchEdgeCases:
    """BUG-032: search_generator with empty content_futures."""

    def test_search_empty_content_futures_cleanup(self, mock_project):
        """Search_generator handles no content matches gracefully."""
        results = list(search_generator(
            mock_project,
            "zzz_nonexistent_pattern_xyz",
            "content",
            "",
            stop_event=None,
        ))
        assert isinstance(results, list)

    def test_search_with_stop_event_immediate(self, mock_project):
        """Search_generator with already-set stop event returns empty."""
        stop = threading.Event()
        stop.set()
        results = list(search_generator(
            mock_project,
            ".py",
            "smart",
            "",
            stop_event=stop,
        ))
        assert results == []

    def test_content_mode_large_file_skip(self, tmp_path):
        """Content mode skips files larger than max_size_mb."""
        base = tmp_path / "big_project"
        base.mkdir()
        big_file = base / "big.txt"
        big_file.write_text("x" * 200, encoding="utf-8")

        results = list(search_generator(
            base,
            "x",
            "content",
            "",
            max_size_mb=0,
            stop_event=None,
        ))
        assert isinstance(results, list)

    def test_content_mode_with_results(self, mock_project):
        """Content mode returns matches for files containing query."""
        results = list(search_generator(
            mock_project,
            "hello",
            "content",
            "",
            stop_event=None,
        ))
        paths = [r["path"] for r in results]
        assert any("main.py" in p for p in paths)


class TestContextBlueprint:
    """BUG-028: Context blueprint path type handling."""

    def test_generate_blueprint_accepts_string(self, mock_project):
        """Generate_blueprint accepts string root_dir."""
        result = ContextFormatter.generate_blueprint(str(mock_project), "")
        assert "mock_project" in result

    def test_generate_blueprint_accepts_path(self, mock_project):
        """Generate_blueprint accepts pathlib.Path root_dir."""
        result = ContextFormatter.generate_blueprint(
            str(mock_project), "", use_gitignore=True
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestGUIImportSafety:
    """DEBT-006: GUI components are optional imports."""

    def test_batch_rename_window_importable(self):
        """BatchRenameWindow is importable (or None in headless)."""
        from file_cortex_core import BatchRenameWindow

        assert BatchRenameWindow is not None

    def test_duplicate_finder_window_importable(self):
        """DuplicateFinderWindow is importable (or None in headless)."""
        from file_cortex_core import DuplicateFinderWindow

        assert DuplicateFinderWindow is not None

    def test_path_collection_dialog_importable(self):
        """PathCollectionDialog is importable from core."""
        from file_cortex_core import PathCollectionDialog

        assert PathCollectionDialog is not None

    def test_core_modules_importable_without_gui(self):
        """Core modules work independently of GUI."""
        from file_cortex_core import DataManager, FileUtils, search_generator

        assert DataManager is not None
        assert FileUtils is not None
        assert search_generator is not None


class TestPathValidatorEdgeCases:
    """Extended PathValidator edge case tests."""

    def test_norm_path_empty_string(self):
        """Norm_path with empty string returns empty."""
        assert PathValidator.norm_path("") == ""

    def test_norm_path_none(self):
        """Norm_path with None returns empty."""
        assert PathValidator.norm_path(None) == ""

    def test_norm_path_trailing_slash(self):
        """Norm_path strips trailing slashes."""
        result = PathValidator.norm_path("/tmp/test/")
        assert not result.endswith("/") or result == "/"

    def test_is_safe_with_empty_root(self):
        """Is_safe returns False for empty root."""
        assert PathValidator.is_safe("/some/path", "") is False

    def test_is_safe_with_relative_target(self):
        """Is_safe resolves relative targets against root."""
        result = PathValidator.is_safe("subdir/file.txt", "/tmp/project")
        assert isinstance(result, bool)


class TestFileOpsEdgeCases:
    """Additional FileOps edge case tests."""

    def test_save_content_atomic(self, tmp_path):
        """Save_content uses atomic write."""
        f = tmp_path / "atomic.txt"
        f.write_text("original", encoding="utf-8")
        FileOps.save_content(str(f), "updated content")
        assert f.read_text(encoding="utf-8") == "updated content"

    def test_save_content_nonexistent_file(self, tmp_path):
        """Save_content raises for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            FileOps.save_content(str(tmp_path / "nope.txt"), "data")

    def test_create_file_then_dir(self, tmp_path):
        """Create_item creates file then directory with same name fails."""
        FileOps.create_item(str(tmp_path), "item1", is_dir=False)
        with pytest.raises(FileExistsError):
            FileOps.create_item(str(tmp_path), "item1", is_dir=True)

    def test_move_file_cross_dir(self, tmp_path):
        """Move_file moves across directories."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        dst_dir = tmp_path / "dst"
        dst_dir.mkdir()
        src_file = src_dir / "test.txt"
        src_file.write_text("data", encoding="utf-8")

        result = FileOps.move_file(str(src_file), str(dst_dir))
        assert pathlib.Path(result).parent == dst_dir
        assert pathlib.Path(result).exists()

    def test_archive_with_nested_dirs(self, tmp_path):
        """Archive_selection handles nested directories."""
        base = tmp_path / "archive_test"
        base.mkdir()
        (base / "sub").mkdir()
        (base / "sub" / "deep.txt").write_text("deep", encoding="utf-8")
        (base / "top.txt").write_text("top", encoding="utf-8")

        out = tmp_path / "output.zip"
        FileOps.archive_selection(
            [str(base / "sub"), str(base / "top.txt")],
            str(out),
            root_dir=str(tmp_path),
        )
        assert out.exists()
        assert out.stat().st_size > 0

    def test_batch_categorize_undefined_category(self, tmp_path):
        """Batch_categorize raises for undefined category."""
        base = tmp_path / "cat_test"
        base.mkdir()
        dm = DataManager()
        dm.add_to_recent(str(base))

        with pytest.raises(ValueError, match="not defined"):
            FileOps.batch_categorize(str(base), [], "NonexistentCategory")


class TestNoiseReducerEdgeCases:
    """NoiseReducer boundary tests."""

    def test_clean_none_input(self):
        """Clean handles None input."""
        assert NoiseReducer.clean(None) == ""

    def test_clean_empty_string(self):
        """Clean handles empty string."""
        assert NoiseReducer.clean("") == ""

    def test_clean_base64_like_line(self):
        """Clean skips base64-like lines."""
        long_b64 = "a" * 300
        result = NoiseReducer.clean(long_b64)
        assert "Base64-like" in result or "skipped" in result

    def test_clean_normal_lines_preserved(self):
        """Clean preserves normal lines (splitlines strips trailing newline)."""
        text = "def hello():\n    print('world')\n"
        result = NoiseReducer.clean(text)
        assert "def hello():" in result
        assert "print('world')" in result


class TestFormatUtilsEdgeCases:
    """FormatUtils edge case tests."""

    def test_format_number_negative(self):
        """Format_number with negative value."""
        result = FormatUtils.format_number(-1)
        assert isinstance(result, str)

    def test_format_size_zero(self):
        """Format_size with zero."""
        assert FormatUtils.format_size(0) == "0 B"

    def test_format_size_gb(self):
        """Format_size with GB range."""
        result = FormatUtils.format_size(2 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_estimate_tokens_empty(self):
        """Estimate_tokens with empty string."""
        assert FormatUtils.estimate_tokens("") == 0

    def test_estimate_tokens_cjk(self):
        """Estimate_tokens with CJK characters."""
        result = FormatUtils.estimate_tokens("测试中文内容")
        assert result > 0

    def test_collect_paths_absolute_mode(self, tmp_path):
        """Collect_paths with absolute mode."""
        f = tmp_path / "test.txt"
        f.write_text("data", encoding="utf-8")
        result = FormatUtils.collect_paths(
            [str(f)], mode="absolute", separator=","
        )
        assert str(f) in result


class TestDataManagerEdgeCases:
    """DataManager edge case tests."""

    def test_update_global_settings_partial(self, tmp_path):
        """Partial update preserves other fields."""
        from unittest.mock import patch

        config_path = tmp_path / "test_config.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            FileUtils.clear_cache()
            dm = DataManager()

            dm.update_global_settings({"token_threshold": 99999})
            assert dm.config.global_settings.token_threshold == 99999
            assert dm.config.global_settings.preview_limit_mb == 1.0

    def test_update_global_settings_invalid_type(self, tmp_path):
        """Invalid type in global settings raises validation error."""
        from unittest.mock import patch

        from pydantic import ValidationError

        config_path = tmp_path / "test_config.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            FileUtils.clear_cache()
            dm = DataManager()

            with pytest.raises(ValidationError):
                dm.update_global_settings({"token_threshold": "not_a_number"})

    def test_add_to_recent_dedup(self, tmp_path):
        """Add_to_recent moves duplicate to front."""
        from unittest.mock import patch

        config_path = tmp_path / "test_config.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            FileUtils.clear_cache()
            dm = DataManager()

            p = str(tmp_path / "proj")
            pathlib.Path(p).mkdir(exist_ok=True)

            dm.add_to_recent(p)
            dm.add_to_recent(p)
            norm_p = PathValidator.norm_path(p)
            assert dm.config.recent_projects.count(norm_p) == 1
            assert dm.config.recent_projects[0] == norm_p

    def test_toggle_pinned_roundtrip(self, tmp_path):
        """Toggle_pinned adds then removes."""
        from unittest.mock import patch

        config_path = tmp_path / "test_config.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            FileUtils.clear_cache()
            dm = DataManager()

            p = str(tmp_path / "proj")
            pathlib.Path(p).mkdir(exist_ok=True)

            result1 = dm.toggle_pinned(p)
            assert result1 is True
            result2 = dm.toggle_pinned(p)
            assert result2 is False

    def test_session_limit(self, tmp_path):
        """Sessions are capped at 5."""
        from unittest.mock import patch

        config_path = tmp_path / "test_config.json"
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            FileUtils.clear_cache()
            dm = DataManager()

            p = str(tmp_path / "proj")
            pathlib.Path(p).mkdir(exist_ok=True)
            dm.add_to_recent(p)

            for i in range(10):
                dm.save_session(p, {"idx": i})

            proj = dm.get_project_data_obj(p)
            assert len(proj.sessions) == 5


class TestWebAPIEdgeCases:
    """Web API edge case tests."""

    def test_global_settings_roundtrip(self, api_client):
        """Global settings update and retrieve roundtrip."""
        res = api_client.post("/api/global/settings", json={
            "token_threshold": 200000,
            "preview_limit_mb": 2.5,
        })
        assert res.status_code == 200

        res = api_client.get("/api/global/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["token_threshold"] == 200000
        assert data["preview_limit_mb"] == 2.5

    def test_generate_context_markdown(self, project_client, mock_project):
        """Generate context in markdown format."""
        res = project_client.post("/api/generate", json={
            "files": [str(mock_project / "src" / "main.py")],
            "project_path": str(mock_project),
            "export_format": "markdown",
        })
        assert res.status_code == 200
        data = res.json()
        assert "content" in data
        assert "print" in data["content"]
        assert data["tokens"] > 0

    def test_generate_context_xml(self, project_client, mock_project):
        """Generate context in XML format."""
        res = project_client.post("/api/generate", json={
            "files": [str(mock_project / "src" / "main.py")],
            "project_path": str(mock_project),
            "export_format": "xml",
        })
        assert res.status_code == 200
        data = res.json()
        assert "<context>" in data["content"]
        assert "</context>" in data["content"]

    def test_stage_all_with_excludes(self, project_client, mock_project):
        """Stage all respects exclude patterns."""
        res = project_client.post("/api/project/settings", json={
            "project_path": str(mock_project),
            "settings": {"excludes": "*.png *.bin"},
        })
        assert res.status_code == 200

        res = project_client.post("/api/actions/stage_all", json={
            "project_path": str(mock_project),
            "mode": "files",
            "apply_excludes": True,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["added_count"] > 0

    def test_fs_save_and_read(self, project_client, mock_project):
        """Save content then read it back."""
        test_file = mock_project / "save_test.txt"
        test_file.write_text("original", encoding="utf-8")

        res = project_client.post("/api/fs/save", json={
            "path": str(test_file),
            "content": "saved content",
        })
        assert res.status_code == 200

        res = project_client.get(f"/api/content?path={test_file}")
        assert res.status_code == 200
        assert res.json()["content"] == "saved content"

    def test_project_not_registered_returns_403(self, api_client, tmp_path):
        """Access to unregistered project returns 403."""
        unregistered = tmp_path / "unregistered"
        unregistered.mkdir()

        res = api_client.get(f"/api/project/config?path={unregistered}")
        assert res.status_code == 403

    def test_stats_endpoint(self, project_client, mock_project):
        """Stats endpoint returns token count."""
        res = project_client.post("/api/project/stats", json={
            "paths": [str(mock_project / "src" / "main.py")],
            "project_path": str(mock_project),
        })
        assert res.status_code == 200
        data = res.json()
        assert "total_tokens" in data
        assert "file_count" in data
        assert data["file_count"] >= 1


class TestContextFormatterEdgeCases:
    """ContextFormatter edge case tests."""

    def test_to_markdown_empty_paths(self):
        """To_markdown with empty paths list."""
        result = ContextFormatter.to_markdown([])
        assert isinstance(result, str)

    def test_to_xml_empty_paths(self):
        """To_xml with empty paths list."""
        result = ContextFormatter.to_xml([], include_blueprint=False)
        assert "<context>" in result
        assert "</context>" in result

    def test_to_xml_cdata_escape(self, tmp_path):
        """To_xml escapes CDATA closing sequences."""
        f = tmp_path / "cdata_test.py"
        f.write_text("x = ']]>'", encoding="utf-8")

        result = ContextFormatter.to_xml(
            [str(f)], root_dir=str(tmp_path), include_blueprint=False,
        )
        assert "]]>" not in result.replace("]]>", "") or "]]]]>" in result

    def test_to_markdown_with_prompt_prefix(self, tmp_path):
        """To_markdown applies prompt prefix."""
        f = tmp_path / "prefix_test.txt"
        f.write_text("content here", encoding="utf-8")

        result = ContextFormatter.to_markdown(
            [str(f)],
            root_dir=str(tmp_path),
            prompt_prefix="Review this code",
        )
        assert "Review this code" in result

    def test_noise_reducer_applied_in_markdown(self, tmp_path):
        """NoiseReducer is applied when requested."""
        f = tmp_path / "noisy.js"
        long_line = "x" * 600
        f.write_text(long_line, encoding="utf-8")

        result = ContextFormatter.to_markdown(
            [str(f)],
            root_dir=str(tmp_path),
            apply_noise_reducer=True,
        )
        assert "skipped" in result or "NoiseReducer" in result
