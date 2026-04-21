import os
import queue
import sys
import threading

import pytest

from file_cortex_core import (
    ActionBridge,
    ContextFormatter,
    DuplicateWorker,
    FileOps,
    FileUtils,
    FormatUtils,
    NoiseReducer,
    PathValidator,
    SearchWorker,
    search_generator,
)


class TestDataManagerAdvanced:
    """Unit tests for previously untested DataManager methods."""

    def test_batch_stage_dedup_and_add(self, clean_config, mock_project):
        """Verify batch_stage deduplicates and adds correctly."""
        dm = clean_config
        p = str(mock_project)
        f1 = str(mock_project / "src" / "main.py")
        f2 = str(mock_project / "config.json")

        added = dm.batch_stage(p, [f1, f2])
        assert added == 2

        added_again = dm.batch_stage(p, [f1])
        assert added_again == 0

        proj = dm.get_project_data(p)
        assert len(proj["staging_list"]) == 2

    def test_save_session_limit(self, clean_config, mock_project):
        """Verify sessions are capped at 5 entries."""
        dm = clean_config
        p = str(mock_project)
        for i in range(8):
            dm.save_session(p, {"index": i})
        proj = dm.get_project_data(p)
        assert len(proj["sessions"]) == 5
        assert proj["sessions"][0]["index"] == 7

    def test_remove_tag(self, clean_config, mock_project):
        """Verify tag removal."""
        dm = clean_config
        p = str(mock_project)
        f = str(mock_project / "src" / "main.py")
        dm.add_tag(p, f, "Priority")
        dm.add_tag(p, f, "Review")
        proj = dm.get_project_data(p)
        assert "Priority" in proj["tags"][PathValidator.norm_path(f)]

        dm.remove_tag(p, f, "Priority")
        proj = dm.get_project_data(p)
        norm_f = PathValidator.norm_path(f)
        assert "Priority" not in proj["tags"][norm_f]
        assert "Review" in proj["tags"][norm_f]

    def test_resolve_project_root_nested(self, clean_config, mock_project):
        """Verify nested path resolution."""
        dm = clean_config
        p = str(mock_project)
        dm.get_project_data(p)

        child = str(mock_project / "src" / "main.py")
        root = dm.resolve_project_root(child)
        assert root is not None
        assert PathValidator.norm_path(root) == PathValidator.norm_path(p)

    def test_resolve_project_root_prefers_most_specific_match(
        self, clean_config, mock_project
    ):
        """Nested registered projects should resolve to the deepest matching root."""
        dm = clean_config
        parent = str(mock_project)
        child_root = str(mock_project / "src")
        dm.get_project_data(parent)
        dm.get_project_data(child_root)

        target = str(mock_project / "src" / "main.py")
        root = dm.resolve_project_root(target)
        assert PathValidator.norm_path(root) == PathValidator.norm_path(child_root)

    def test_resolve_project_root_unknown_returns_none(self, clean_config):
        """Unregistered path returns None."""
        dm = clean_config
        assert dm.resolve_project_root("/nonexistent/path/xyz") is None

    def test_toggle_pinned_roundtrip(self, clean_config, mock_project):
        """Verify pin toggle returns correct state."""
        dm = clean_config
        p = PathValidator.norm_path(str(mock_project))
        os.makedirs(p, exist_ok=True)

        status1 = dm.toggle_pinned(p)
        assert status1 is True
        assert p in dm.data["pinned_projects"]

        status2 = dm.toggle_pinned(p)
        assert status2 is False
        assert p not in dm.data["pinned_projects"]

    def test_update_custom_tools_validation(self, clean_config, mock_project):
        """Verify custom tools validation rejects bad input."""
        dm = clean_config
        p = str(mock_project)

        with pytest.raises(ValueError):
            dm.update_custom_tools(p, "not_a_dict")

        with pytest.raises(ValueError):
            dm.update_custom_tools(p, {123: "cmd"})

    def test_get_workspaces_summary(self, clean_config, mock_project):
        """Verify workspace summary structure."""
        dm = clean_config
        p = PathValidator.norm_path(str(mock_project))
        dm.add_to_recent(p)
        summary = dm.get_workspaces_summary()
        assert "pinned" in summary
        assert "recent" in summary
        assert any(item["path"] == p for item in summary["recent"])

    def test_mutable_settings_whitelist(self, clean_config, mock_project):
        """Verify protected keys are blocked."""
        dm = clean_config
        p = str(mock_project)
        dm.update_project_settings(p, {"groups": {"evil": []}})
        proj = dm.get_project_data(p)
        assert "evil" not in proj.get("groups", {})

        dm.update_project_settings(p, {"notes": {"leak": "data"}})
        proj = dm.get_project_data(p)
        assert "leak" not in proj.get("notes", {})


class TestPathValidatorAdvanced:
    """Extended tests for PathValidator."""

    def test_validate_project_unc_blocked(self):
        """UNC paths raise PermissionError."""
        with pytest.raises(PermissionError, match="UNC"):
            PathValidator.validate_project("\\\\server\\share")

    def test_validate_project_sensitive_dir(self, tmp_path):
        """Sensitive directory names are rejected."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with pytest.raises(PermissionError, match="sensitive"):
            PathValidator.validate_project(str(git_dir))

    def test_validate_project_not_found(self):
        """Non-existent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PathValidator.validate_project("/nonexistent_xyz_path_12345")

    def test_validate_project_file_not_dir(self, tmp_path):
        """File path raises NotADirectoryError."""
        f = tmp_path / "notadir.txt"
        f.write_text("test")
        with pytest.raises(NotADirectoryError):
            PathValidator.validate_project(str(f))

    def test_validate_project_valid(self, tmp_path):
        """Valid directory returns Path."""
        result = PathValidator.validate_project(str(tmp_path))
        assert result.exists()
        assert result.is_dir()

    def test_norm_path_empty_and_none(self):
        """Edge cases: empty and None return empty string."""
        assert PathValidator.norm_path("") == ""
        assert PathValidator.norm_path(None) == ""

    def test_norm_path_root(self):
        """Root path normalization."""
        if sys.platform == "win32":
            result = PathValidator.norm_path("C:/")
            assert result == "c:/"
        else:
            assert PathValidator.norm_path("/") == "/"


class TestSearchWorkerAndAdvanced:
    """Tests for SearchWorker and advanced search scenarios."""

    def test_search_worker_produces_results(self, mock_project):
        """Verify SearchWorker sends results via queue."""
        q = queue.Queue()
        stop = threading.Event()
        worker = SearchWorker(
            root_dir=mock_project,
            search_text="main",
            search_mode="smart",
            manual_excludes="",
            include_dirs=False,
            result_queue=q,
            stop_event=stop,
        )
        worker.run()
        results = []
        while not q.empty():
            item = q.get()
            if isinstance(item, tuple) and item[0] == "DONE":
                break
            results.append(item)
        assert len(results) >= 1

    def test_search_include_dirs(self, mock_project):
        """Verify include_dirs=True returns directories."""
        results = list(search_generator(
            str(mock_project), "", "smart", "",
            include_dirs=True, positive_tags=["src"]
        ))
        types = [r.get("match_type", "") for r in results]
        assert any("Folder" in t for t in types)

    def test_search_content_mode_case_sensitive(self, mock_project):
        """Content search with case sensitivity."""
        results_lower = list(search_generator(
            str(mock_project), "hello", "content", "",
            case_sensitive=False
        ))
        results_upper = list(search_generator(
            str(mock_project), "HELLO", "content", "",
            case_sensitive=True
        ))
        assert len(results_lower) >= 1
        assert len(results_upper) == 0

    def test_search_empty_query_no_tags(self, mock_project):
        """Empty query with no tags yields nothing."""
        results = list(search_generator(
            str(mock_project), "", "smart", ""
        ))
        assert len(results) == 0

    def test_search_regex_invalid_pattern(self, mock_project):
        """Invalid regex pattern returns empty."""
        results = list(search_generator(
            str(mock_project), "[unclosed", "regex", ""
        ))
        assert len(results) == 0

    def test_search_negative_tags_only(self, mock_project):
        """Negative tags without positive tags or query."""
        results = list(search_generator(
            str(mock_project), "", "smart", "",
            negative_tags=["main"]
        ))
        paths = [r["path"] for r in results]
        assert not any("main" in p for p in paths)

    @pytest.mark.parametrize("max_results", [1, 5])
    def test_search_max_results_boundary(self, stress_project, max_results):
        """Verify exact max_results boundary."""
        results = list(search_generator(
            str(stress_project), "file", "smart", "",
            max_results=max_results
        ))
        assert len(results) == max_results


class TestFileOpsAdvanced:
    """Advanced file operation tests."""

    def test_rename_file_success(self, tmp_path):
        """Verify successful rename returns new path."""
        f = tmp_path / "old.txt"
        f.write_text("data")
        result = FileOps.rename_file(str(f), "new.txt")
        assert "new.txt" in result
        assert (tmp_path / "new.txt").exists()
        assert not (tmp_path / "old.txt").exists()

    def test_rename_file_nonexistent(self, tmp_path):
        """Rename non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            FileOps.rename_file(str(tmp_path / "ghost.txt"), "new.txt")

    def test_move_file_success(self, tmp_path):
        """Verify successful file move."""
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        f = src_dir / "test.txt"
        f.write_text("content")

        FileOps.move_file(str(f), str(dst_dir))
        assert (dst_dir / "test.txt").exists()
        assert not f.exists()

    def test_delete_directory(self, tmp_path):
        """Verify directory deletion."""
        d = tmp_path / "to_delete"
        d.mkdir()
        (d / "inner.txt").write_text("x")
        FileOps.delete_file(str(d))
        assert not d.exists()

    def test_delete_nonexistent(self, tmp_path):
        """Delete non-existent raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            FileOps.delete_file(str(tmp_path / "ghost.txt"))

    def test_save_content_to_nonexistent(self, tmp_path):
        """Save to non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            FileOps.save_content(str(tmp_path / "ghost.txt"), "data")

    def test_save_content_empty_string(self, tmp_path):
        """Save empty content works."""
        f = tmp_path / "empty.txt"
        f.write_text("old", encoding="utf-8")
        FileOps.save_content(str(f), "")
        assert f.read_text(encoding="utf-8") == ""

    def test_archive_nested_structure(self, tmp_path):
        """Verify ZIP with nested directories."""
        nested = tmp_path / "project"
        nested.mkdir()
        (nested / "src").mkdir()
        (nested / "src" / "app.py").write_text("print('hi')")
        (nested / "README.md").write_text("# Test")

        out = tmp_path / "test.zip"
        FileOps.archive_selection(
            [str(nested / "src" / "app.py"), str(nested / "README.md")],
            str(out),
            str(nested),
        )
        import zipfile
        with zipfile.ZipFile(str(out)) as z:
            names = z.namelist()
            assert any("app.py" in n for n in names)
            assert any("README" in n for n in names)

    def test_batch_rename_conflict_counter(self, tmp_path):
        """Verify conflict resolution adds counter suffix."""
        for name in ["a.txt", "b.txt"]:
            (tmp_path / name).write_text("x")
        results = FileOps.batch_rename(
            str(tmp_path),
            [str(tmp_path / "a.txt"), str(tmp_path / "b.txt")],
            r".*\.txt", "renamed.txt",
            dry_run=True,
        )
        statuses = [r["status"] for r in results]
        assert "ok" in statuses
        assert "renamed_with_suffix" in statuses


class TestActionBridgeAdvanced:
    """Advanced ActionBridge tests."""

    def test_execute_tool_success(self, mock_project):
        """Verify tool execution returns result dict."""
        import sys
        test_f = mock_project / "src" / "main.py"
        template = f'"{sys.executable}" -c "print(\'OK\')"'
        result = ActionBridge.execute_tool(template, str(test_f), str(mock_project))
        assert result["status"] == "success"
        assert "OK" in result["stdout"]

    def test_execute_tool_nonexistent_path(self, tmp_path):
        """Non-existent file returns error."""
        result = ActionBridge.execute_tool(
            "echo {path}", str(tmp_path / "ghost.txt"), str(tmp_path)
        )
        assert result["status"] == "error"


class TestDuplicateWorkerAdvanced:
    """Advanced duplicate detection tests."""

    def test_duplicate_with_excludes(self, tmp_path):
        """Verify duplicate worker respects excludes."""
        (tmp_path / "a.txt").write_text("SAME")
        (tmp_path / "b.txt").write_text("SAME")
        ignored = tmp_path / "ignored.txt"
        ignored.write_text("SAME")

        q = queue.Queue()
        stop = threading.Event()
        worker = DuplicateWorker(
            str(tmp_path), "ignored*", True, q, stop
        )
        worker.run()

        results = []
        while not q.empty():
            item = q.get()
            if isinstance(item, dict):
                results.append(item)
        all_paths = []
        for r in results:
            all_paths.extend(r["paths"])
        assert not any("ignored" in p for p in all_paths)

    def test_hash_cancellation(self, tmp_path):
        """Verify stop_event cancels hashing."""
        big = tmp_path / "big.bin"
        big.write_bytes(b"\x00" * 1024)

        q = queue.Queue()
        stop = threading.Event()
        stop.set()

        worker = DuplicateWorker(str(tmp_path), "", True, q, stop)
        worker.run()

        results = []
        while not q.empty():
            item = q.get()
            if isinstance(item, dict):
                results.append(item)
        assert len(results) == 0


class TestUtilsAdvanced:
    """Advanced utility tests."""

    def test_collect_paths_with_prefix_suffix(self, mock_project):
        """Verify path collection with prefix and suffix."""
        f = str(mock_project / "src" / "main.py")
        result = FormatUtils.collect_paths(
            [f], root_dir=str(mock_project),
            mode="relative", separator=" ",
            file_prefix="@", dir_suffix="/",
        )
        assert result.startswith("@")

    def test_collect_paths_custom_separator(self, mock_project):
        """Verify custom separator."""
        f1 = str(mock_project / "src" / "main.py")
        f2 = str(mock_project / "config.json")
        result = FormatUtils.collect_paths(
            [f1, f2], root_dir=str(mock_project),
            mode="relative", separator=" | ",
        )
        assert " | " in result

    def test_flatten_paths_empty_input(self):
        """Empty input returns empty list."""
        assert FileUtils.flatten_paths([]) == []

    def test_flatten_paths_directory_expansion(self, tmp_path):
        """Verify directory gets expanded to individual files."""
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "a.py").write_text("a")
        (d / "b.py").write_text("b")

        result = FileUtils.flatten_paths([str(d)])
        assert len(result) == 2

    def test_generate_blueprint(self, mock_project):
        """Verify blueprint generation."""
        bp = ContextFormatter.generate_blueprint(str(mock_project), "")
        assert "mock_project" in bp
        assert "src" in bp

    def test_noise_reducer_default_max_line(self):
        """Verify default max_line_length=500."""
        long_line = "x" * 501
        result = NoiseReducer.clean(long_line)
        assert "skipped" in result

    def test_get_metadata_keys(self, tmp_path):
        """Verify metadata dict contains all expected keys."""
        f = tmp_path / "test.py"
        f.write_text("print('hi')")
        meta = FileUtils.get_metadata(f)
        for key in ["name", "path", "abs_path", "type", "size", "size_fmt",
                     "mtime", "mtime_fmt", "ext"]:
            assert key in meta

    def test_format_datetime_current(self):
        """Verify format_datetime with current time."""
        import time
        result = FormatUtils.format_datetime(time.time())
        assert "20" in result
        assert len(result) > 0
