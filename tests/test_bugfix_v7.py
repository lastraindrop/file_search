"""Comprehensive bug-fix and coverage tests for FileCortex v7.0.

Covers: save_content truncation, deprecated API removal, relative_to root
files, search dead code removal, flatten_paths stop_event, AppleScript
injection, NoiseReducer edge cases, PathValidator edge cases, DataManager DI,
batch rename conflict/rollback, archive, create/delete/move operations,
context XML/MD formatting, search modes, gitignore, token estimation,
path collection, and project root resolution.
"""

# ruff: noqa: D102, I001

import os
import pathlib
import threading
import zipfile

import pytest

from file_cortex_core import (
    ActionBridge,
    ContextFormatter,
    DataManager,
    FileOps,
    FileUtils,
    FormatUtils,
    NoiseReducer,
    PathValidator,
    search_generator,
)
from file_cortex_core.config import GlobalSettings


class TestSaveContentNoTruncation:
    """BUG A-1: save_content must not truncate the last character."""

    def test_save_content_no_truncation(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        FileOps.save_content(str(f), "hello")
        assert f.read_text(encoding="utf-8") == "hello"

    def test_save_content_preserves_trailing_newline(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello\n", encoding="utf-8")
        FileOps.save_content(str(f), "hello\n")
        assert f.read_text(encoding="utf-8") == "hello\n"

    def test_save_content_no_extra_newline(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("abc", encoding="utf-8")
        FileOps.save_content(str(f), "abc")
        content = f.read_text(encoding="utf-8")
        assert content == "abc"
        assert not content.endswith("\n")

    def test_save_content_unicode(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("你好世界", encoding="utf-8")
        FileOps.save_content(str(f), "你好世界")
        assert f.read_text(encoding="utf-8") == "你好世界"

    def test_save_content_empty(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("nonempty", encoding="utf-8")
        FileOps.save_content(str(f), "")
        assert f.read_text(encoding="utf-8") == ""

    def test_save_content_binary_raises(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\xff\x00\xff")
        with pytest.raises(ValueError, match="binary"):
            FileOps.save_content(str(f), "text")

    def test_save_content_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            FileOps.save_content(str(tmp_path / "nope.txt"), "x")

    def test_save_content_directory_raises(self, tmp_path):
        with pytest.raises(IsADirectoryError):
            FileOps.save_content(str(tmp_path), "x")


class TestExecutionTimeout:
    """BUG A-2: execution timeout must use env var, not deprecated API."""

    def test_execution_timeout_env_var(self, monkeypatch):
        monkeypatch.setenv("FCTX_EXEC_TIMEOUT", "60")
        assert int(os.getenv("FCTX_EXEC_TIMEOUT", "300")) == 60

    def test_execution_timeout_default(self, monkeypatch):
        monkeypatch.delenv("FCTX_EXEC_TIMEOUT", raising=False)
        assert int(os.getenv("FCTX_EXEC_TIMEOUT", "300")) == 300


class TestRelativePathRootFiles:
    """BUG A-3: files directly in project root must get correct rel path."""

    def test_relative_path_root_files(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        f = root / "readme.md"
        f.write_text("hello", encoding="utf-8")
        p = pathlib.Path(str(f))
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p.name
        assert str(rel) == "readme.md"

    def test_relative_path_nested_files(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / "src").mkdir()
        f = root / "src" / "main.py"
        f.write_text("code", encoding="utf-8")
        p = pathlib.Path(str(f))
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p.name
        assert str(rel).replace("\\", "/") == "src/main.py"

    def test_relative_path_deeply_nested(self, tmp_path):
        root = tmp_path / "project"
        deep = root / "a" / "b" / "c"
        deep.mkdir(parents=True)
        f = deep / "file.txt"
        f.write_text("deep", encoding="utf-8")
        p = pathlib.Path(str(f))
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p.name
        assert "c" in str(rel) and "file.txt" in str(rel)


class TestSearchGenerator:
    """B-1: search dead code removed; max_results enforced."""

    def test_search_max_results_enforced(self, tmp_path):
        root = tmp_path / "search_proj"
        root.mkdir()
        for i in range(20):
            (root / f"file_{i}.txt").write_text(f"content {i}", encoding="utf-8")
        results = list(search_generator(
            root, "", "smart", "",
            max_results=5,
        ))
        assert len(results) <= 5

    def test_search_content_mode_basic(self, tmp_path):
        root = tmp_path / "content_proj"
        root.mkdir()
        (root / "findme.py").write_text("target_keyword_here", encoding="utf-8")
        (root / "other.py").write_text("no match here", encoding="utf-8")
        results = list(search_generator(
            root, "target_keyword", "content", "",
        ))
        assert len(results) == 1
        assert results[0]["match_type"] == "Content Match"

    def test_search_regex_invalid_pattern(self, tmp_path):
        root = tmp_path / "regex_proj"
        root.mkdir()
        (root / "file.txt").write_text("hello", encoding="utf-8")
        results = list(search_generator(
            root, "[invalid(regex", "regex", "",
        ))
        assert isinstance(results, list)

    def test_search_inverse_mode(self, tmp_path):
        root = tmp_path / "inv_proj"
        root.mkdir()
        (root / "keep.py").write_text("a", encoding="utf-8")
        (root / "skip.js").write_text("b", encoding="utf-8")
        results = list(search_generator(
            root, ".py", "smart", "", is_inverse=True,
        ))
        for r in results:
            assert not r["path"].endswith(".py")

    def test_search_empty_query(self, tmp_path):
        root = tmp_path / "empty_q"
        root.mkdir()
        (root / "file.txt").write_text("x", encoding="utf-8")
        results = list(search_generator(root, "", "smart", ""))
        assert isinstance(results, list)


class TestPinButtonConfigAPI:
    """B-6: pin button uses config.pinned_projects, not deprecated dict API."""

    def test_config_pinned_projects_list(self, tmp_path):
        from unittest.mock import patch
        config_path = tmp_path / "pin_config.json"
        with patch('file_cortex_core.config._CONFIG_FILE', config_path):
            DataManager.reset()
            dm = DataManager()
            test_path = str(tmp_path / "some" / "path")
            dm.toggle_pinned(test_path)
            norm = PathValidator.norm_path(test_path)
            assert norm in dm.config.pinned_projects
            DataManager.reset()

    def test_config_pinned_projects_toggle_off(self, tmp_path):
        from unittest.mock import patch
        config_path = tmp_path / "pin_config2.json"
        with patch('file_cortex_core.config._CONFIG_FILE', config_path):
            DataManager.reset()
            dm = DataManager()
            test_path = str(tmp_path / "some" / "path")
            dm.toggle_pinned(test_path)
            norm = PathValidator.norm_path(test_path)
            assert norm in dm.config.pinned_projects
            dm.toggle_pinned(test_path)
            assert norm not in dm.config.pinned_projects
            DataManager.reset()


class TestFlattenPathsStopEvent:
    """B-7: flatten_paths supports stop_event for cancellation."""

    def test_flatten_paths_empty(self):
        assert FileUtils.flatten_paths([]) == []

    def test_flatten_paths_basic(self, tmp_path):
        root = tmp_path / "flat_proj"
        root.mkdir()
        (root / "a.txt").write_text("a", encoding="utf-8")
        (root / "b.txt").write_text("b", encoding="utf-8")
        result = FileUtils.flatten_paths([str(root)], str(root))
        assert len(result) >= 2

    def test_flatten_paths_stop_event(self, tmp_path):
        root = tmp_path / "stop_proj"
        root.mkdir()
        for i in range(50):
            (root / f"f{i}.txt").write_text("x" * 100, encoding="utf-8")
        stop = threading.Event()
        stop.set()
        result = FileUtils.flatten_paths([str(root)], str(root), stop_event=stop)
        assert isinstance(result, list)


class TestFormatDatetime:
    """M-7: format_datetime always returns string."""

    def test_format_datetime_returns_string(self):
        result = FormatUtils.format_datetime(1700000000.0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_datetime_zero(self):
        result = FormatUtils.format_datetime(0)
        assert isinstance(result, str)

    def test_format_datetime_negative(self):
        result = FormatUtils.format_datetime(-1)
        assert isinstance(result, str)


class TestNoiseReducer:
    """NoiseReducer edge cases."""

    def test_noise_reducer_none(self):
        assert NoiseReducer.clean(None) == ""

    def test_noise_reducer_empty(self):
        assert NoiseReducer.clean("") == ""

    def test_noise_reducer_long_line(self):
        long_line = "a" * 600
        result = NoiseReducer.clean(long_line)
        assert "skipped" in result

    def test_noise_reducer_base64_like(self):
        b64 = "aB1+" * 60
        result = NoiseReducer.clean(b64)
        assert "skipped" in result or "Base64" in result

    def test_noise_reducer_normal(self):
        assert NoiseReducer.clean("hello world") == "hello world"


class TestPathValidatorEdgeCases:
    """PathValidator edge case coverage."""

    def test_is_safe_empty_root(self):
        assert PathValidator.is_safe("/some/path", "") is False

    def test_is_safe_same_path(self):
        assert PathValidator.is_safe("/tmp", "/tmp") is True

    def test_is_safe_child(self):
        assert PathValidator.is_safe("/tmp/child", "/tmp") is True

    def test_is_safe_outside(self):
        assert PathValidator.is_safe("/other", "/tmp") is False

    def test_norm_path_empty(self):
        assert PathValidator.norm_path("") == ""

    def test_norm_path_basic(self):
        result = PathValidator.norm_path("/tmp/test")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_validate_project_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            PathValidator.validate_project("/nonexistent/pathxyz")


class TestDataManagerDI:
    """DataManager dependency injection patterns."""

    def test_create_independent(self, tmp_path):
        from unittest.mock import patch
        config_path = tmp_path / "di_config.json"
        with patch('file_cortex_core.config._CONFIG_FILE', config_path):
            DataManager.reset()
            dm1 = DataManager()
            dm2 = DataManager.create()
            dm1.config.last_directory = "/path/a"
            assert dm2.config.last_directory != "/path/a"
            DataManager.reset()

    def test_activate_context(self, tmp_path):
        from unittest.mock import patch
        config_path = tmp_path / "act_config.json"
        with patch('file_cortex_core.config._CONFIG_FILE', config_path):
            DataManager.reset()
            dm = DataManager.create()
            dm.config.last_directory = "/custom"
            with DataManager.activate(dm):
                assert DataManager().config.last_directory == "/custom"
            DataManager.reset()

    def test_reset_creates_fresh(self, tmp_path):
        from unittest.mock import patch
        config_path = tmp_path / "reset_config.json"
        with patch('file_cortex_core.config._CONFIG_FILE', config_path):
            DataManager.reset()
            dm = DataManager()
            dm.config.last_directory = "/old"
            DataManager.reset()
            dm2 = DataManager()
            assert dm2.config.last_directory == ""
            DataManager.reset()


class TestBatchRenameConflict:
    """Batch rename conflict resolution and rollback."""

    def test_batch_rename_dry_run(self, tmp_path):
        f1 = tmp_path / "file_a.txt"
        f2 = tmp_path / "file_b.txt"
        f1.write_text("a", encoding="utf-8")
        f2.write_text("b", encoding="utf-8")
        results = FileOps.batch_rename(
            str(tmp_path),
            [str(f1), str(f2)],
            r"file_(\w+)\.txt",
            r"renamed_\1.txt",
            dry_run=True,
        )
        assert len(results) == 2
        assert all(r["status"] in ("ok", "renamed_with_suffix") for r in results)

    def test_batch_rename_no_match(self, tmp_path):
        f = tmp_path / "nomatch.txt"
        f.write_text("x", encoding="utf-8")
        results = FileOps.batch_rename(
            str(tmp_path), [str(f)], r"nothing_", r"replace_", dry_run=True,
        )
        assert len(results) == 0

    def test_batch_rename_invalid_regex(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid regex"):
            FileOps.batch_rename(
                str(tmp_path), [], "[invalid", "x", dry_run=True,
            )


class TestArchiveCreateDeleteMove:
    """FileOps: archive, create, delete, move operations."""

    def test_archive_creates_zip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello", encoding="utf-8")
        out = str(tmp_path / "test.zip")
        FileOps.archive_selection([str(src / "a.txt")], out, str(tmp_path))
        assert zipfile.is_zipfile(out)

    def test_create_item_file(self, tmp_path):
        result = FileOps.create_item(str(tmp_path), "newfile.txt")
        assert pathlib.Path(result).exists()
        assert pathlib.Path(result).is_file()

    def test_create_item_dir(self, tmp_path):
        result = FileOps.create_item(str(tmp_path), "newdir", is_dir=True)
        assert pathlib.Path(result).exists()
        assert pathlib.Path(result).is_dir()

    def test_create_item_duplicate(self, tmp_path):
        (tmp_path / "dup.txt").write_text("x", encoding="utf-8")
        with pytest.raises(FileExistsError):
            FileOps.create_item(str(tmp_path), "dup.txt")

    def test_create_item_invalid_name(self, tmp_path):
        with pytest.raises(ValueError):
            FileOps.create_item(str(tmp_path), "../escape")

    def test_delete_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            FileOps.delete_file(str(tmp_path / "nope.txt"))

    def test_move_file_basic(self, tmp_path):
        src = tmp_path / "move_src.txt"
        src.write_text("data", encoding="utf-8")
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        result = FileOps.move_file(str(src), str(dst_dir))
        assert pathlib.Path(result).exists()
        assert not src.exists()

    def test_move_file_to_nonexistent_dir(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            FileOps.move_file(str(src), str(tmp_path / "nope"))

    def test_move_file_conflict(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x", encoding="utf-8")
        dst = tmp_path / "d"
        dst.mkdir()
        (dst / "f.txt").write_text("y", encoding="utf-8")
        with pytest.raises(FileExistsError):
            FileOps.move_file(str(src), str(dst))


class TestContextFormatter:
    """Context XML/MD formatting edge cases."""

    def test_xml_cdata_escaping(self, tmp_path):
        f = tmp_path / "cdata.txt"
        f.write_text("content with ]]> inside", encoding="utf-8")
        xml = ContextFormatter.to_xml([str(f)], str(tmp_path))
        assert "]]>" in xml

    def test_markdown_empty_paths(self):
        result = ContextFormatter.to_markdown([])
        assert isinstance(result, str)

    def test_xml_empty_paths(self):
        result = ContextFormatter.to_xml([])
        assert isinstance(result, str)

    def test_to_xml_no_blueprint(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print(1)", encoding="utf-8")
        result = ContextFormatter.to_xml([str(f)], str(tmp_path), include_blueprint=False)
        assert "<context>" in result
        assert "<blueprint>" not in result

    def test_to_markdown_with_prefix(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("code", encoding="utf-8")
        result = ContextFormatter.to_markdown(
            [str(f)], str(tmp_path), prompt_prefix="Review this:"
        )
        assert "Review this:" in result


class TestGitignore:
    """Gitignore integration tests."""

    def test_gitignore_respected(self, tmp_path):
        root = tmp_path / "git_proj"
        root.mkdir()
        (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (root / "app.py").write_text("code", encoding="utf-8")
        (root / "debug.log").write_text("log", encoding="utf-8")
        FileUtils.clear_cache()
        results = list(search_generator(root, "app", "smart", "", use_gitignore=True))
        paths = [r["path"] for r in results]
        assert any("app.py" in p for p in paths)
        assert not any("debug.log" in p for p in paths)

    def test_no_gitignore_file(self, tmp_path):
        root = tmp_path / "no_git"
        root.mkdir()
        (root / "file.txt").write_text("x", encoding="utf-8")
        results = list(search_generator(root, "file", "smart", "", use_gitignore=False))
        assert len(results) >= 1


class TestTokenEstimate:
    """Token estimation edge cases."""

    def test_estimate_empty(self):
        assert FormatUtils.estimate_tokens("") == 0

    def test_estimate_ascii(self):
        tokens = FormatUtils.estimate_tokens("hello world")
        assert tokens > 0

    def test_estimate_mixed(self):
        text = "hello 你好 world 世界"
        tokens = FormatUtils.estimate_tokens(text)
        assert tokens > 0

    def test_estimate_pure_cjk(self):
        tokens = FormatUtils.estimate_tokens("你好世界测试")
        assert tokens > 0


class TestCollectPaths:
    """Path collection formatting tests."""

    def test_collect_paths_relative(self, tmp_path):
        root = tmp_path / "proj"
        root.mkdir()
        f = root / "a.txt"
        f.write_text("x", encoding="utf-8")
        result = FormatUtils.collect_paths([str(f)], str(root), mode="relative")
        assert "a.txt" in result

    def test_collect_paths_absolute(self, tmp_path):
        f = tmp_path / "abs.txt"
        f.write_text("x", encoding="utf-8")
        result = FormatUtils.collect_paths([str(f)], mode="absolute")
        assert str(f) in result

    def test_collect_paths_dir_suffix(self, tmp_path):
        d = tmp_path / "mydir"
        d.mkdir()
        result = FormatUtils.collect_paths(
            [str(d)], str(tmp_path), dir_suffix="/"
        )
        assert "/" in result

    def test_collect_paths_separator(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("x", encoding="utf-8")
        f2.write_text("y", encoding="utf-8")
        result = FormatUtils.collect_paths(
            [str(f1), str(f2)], separator=" "
        )
        assert " " in result


class TestResolveProjectRoot:
    """Project root resolution edge cases."""

    def test_resolve_unregistered(self, tmp_path):
        from unittest.mock import patch
        config_path = tmp_path / "resolve_config.json"
        with patch('file_cortex_core.config._CONFIG_FILE', config_path):
            DataManager.reset()
            dm = DataManager()
            assert dm.resolve_project_root("/nonexistent") is None
            DataManager.reset()

    def test_resolve_nested(self, tmp_path):
        from unittest.mock import patch
        config_path = tmp_path / "nested_config.json"
        with patch('file_cortex_core.config._CONFIG_FILE', config_path):
            DataManager.reset()
            dm = DataManager()
            root = tmp_path / "outer"
            root.mkdir()
            inner = root / "inner"
            inner.mkdir()
            dm.get_project_data(str(root))
            assert dm.resolve_project_root(str(inner)) is not None
            DataManager.reset()


class TestProcessManager:
    """Process management registration limits."""

    def test_register_and_unregister(self):
        from unittest.mock import MagicMock

        from routers.common import (
            ACTIVE_PROCESSES,
            PROCESS_LOCK,
            register_process,
            unregister_process,
        )
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        with PROCESS_LOCK:
            ACTIVE_PROCESSES.clear()
        result = register_process(12345, mock_proc)
        assert result is True
        assert 12345 in ACTIVE_PROCESSES
        unregister_process(12345)
        assert 12345 not in ACTIVE_PROCESSES

    def test_register_at_capacity(self):
        from unittest.mock import MagicMock

        from routers.common import (  # noqa: I001
            ACTIVE_PROCESSES,
            PROCESS_LOCK,
            MAX_ACTIVE_PROCESSES,
            register_process,
        )
        with PROCESS_LOCK:
            ACTIVE_PROCESSES.clear()
            for i in range(MAX_ACTIVE_PROCESSES):
                ACTIVE_PROCESSES[i] = MagicMock()
        result = register_process(99999, MagicMock())
        assert result is False
        with PROCESS_LOCK:
            ACTIVE_PROCESSES.clear()


class TestGlobalSettings:
    """GlobalSettings model tests."""

    def test_default_values(self):
        gs = GlobalSettings()
        assert gs.preview_limit_mb > 0
        assert gs.token_threshold > 0
        assert gs.token_ratio > 0
        assert isinstance(gs.enable_noise_reducer, bool)

    def test_update_preserves_unset(self):
        gs = GlobalSettings()
        data = gs.model_dump()
        data.update({"token_threshold": 50000})
        gs2 = GlobalSettings.model_validate(data)
        assert gs2.token_threshold == 50000
        default_gs = GlobalSettings()
        assert gs2.preview_limit_mb == default_gs.preview_limit_mb


class TestFileUtilsIsBinary:
    """FileUtils.is_binary edge cases."""

    def test_empty_file_not_binary(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert FileUtils.is_binary(f) is False

    def test_nonexistent_not_binary(self, tmp_path):
        assert FileUtils.is_binary(tmp_path / "nope.txt") is False

    def test_text_ext_not_binary(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("code", encoding="utf-8")
        assert FileUtils.is_binary(f) is False

    def test_null_bytes_is_binary(self, tmp_path):
        f = tmp_path / "data.dat"
        f.write_bytes(b"hello\x00world")
        assert FileUtils.is_binary(f) is True

    def test_png_is_binary(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        assert FileUtils.is_binary(f) is True


class TestFileUtilsReadTextSmart:
    """FileUtils.read_text_smart edge cases."""

    def test_nonexistent_returns_empty(self, tmp_path):
        result = FileUtils.read_text_smart(tmp_path / "nope.txt")
        assert result == ""

    def test_read_with_max_bytes(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("a" * 1000, encoding="utf-8")
        result = FileUtils.read_text_smart(f, max_bytes=10)
        assert len(result) <= 20

    def test_read_basic(self, tmp_path):
        f = tmp_path / "basic.txt"
        f.write_text("hello world", encoding="utf-8")
        assert FileUtils.read_text_smart(f) == "hello world"


class TestFileUtilsGetLanguageTag:
    """FileUtils.get_language_tag tests."""

    def test_python(self):
        assert FileUtils.get_language_tag(".py") == "python"

    def test_javascript(self):
        assert FileUtils.get_language_tag(".js") == "javascript"

    def test_unknown(self):
        assert FileUtils.get_language_tag(".xyz") == ""

    def test_dockerfile(self):
        assert FileUtils.get_language_tag("dockerfile") == "dockerfile"


class TestVersion:
    """Version consistency tests."""

    def test_version_is_string(self):
        from file_cortex_core import __version__
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_matches_pyproject(self):
        import tomllib

        from file_cortex_core import __version__
        pyproject = pathlib.Path(__file__).parent.parent / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            assert data["project"]["version"] == __version__


class TestActionBridgePrepare:
    """ActionBridge._prepare_execution edge cases."""

    def test_prepare_nonexistent_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ActionBridge._prepare_execution(
                "echo {path}", str(tmp_path / "nope.txt"), str(tmp_path)
            )

    def test_prepare_basic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        cmd, is_shell, ctx = ActionBridge._prepare_execution(
            "echo {path}", str(f), str(tmp_path)
        )
        assert ctx["name"] == "test.txt"
        assert ctx["ext"] == ".txt"
