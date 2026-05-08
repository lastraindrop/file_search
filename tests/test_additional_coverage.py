"""Additional tests for uncovered edge cases and regression prevention."""

import os
import pathlib

import pytest

from file_cortex_core import (
    FileOps,
    FileUtils,
    FormatUtils,
    NoiseReducer,
    PathValidator,
    search_generator,
)


class TestSearchEdgeCases:
    """Edge cases for search module."""

    def test_search_content_mode_empty_file(self, mock_project):
        """Content search on empty file should not crash."""
        empty = mock_project / "empty.txt"
        empty.write_text("", encoding="utf-8")
        results = list(
            search_generator(
                str(mock_project),
                "hello",
                "content",
                "",
            )
        )
        assert isinstance(results, list)

    def test_search_regex_mode_with_tags(self, mock_project):
        """Regex mode with positive/negative tags."""
        results = list(
            search_generator(
                str(mock_project),
                r"\.py$",
                "regex",
                "",
                positive_tags=["main"],
                negative_tags=["config"],
            )
        )
        paths = [r["path"] for r in results]
        assert any("main.py" in p for p in paths)

    def test_search_smart_multi_keyword(self, mock_project):
        """Smart mode with multiple keywords should require all."""
        results = list(
            search_generator(
                str(mock_project),
                "main py",
                "smart",
                "",
            )
        )
        for r in results:
            assert "main" in r["path"].lower() or "main" in r.get("ext", "").lower()

    def test_search_max_results_enforcement(self, stress_project):
        """Search should respect max_results limit."""
        results = list(
            search_generator(
                str(stress_project),
                "file",
                "smart",
                "",
                max_results=3,
            )
        )
        assert len(results) <= 3

    def test_search_empty_query_returns_nothing(self, mock_project):
        """Empty query with no tags returns nothing."""
        results = list(
            search_generator(
                str(mock_project),
                "",
                "smart",
                "",
            )
        )
        assert len(results) == 0


class TestFileIOEdgeCases:
    """Edge cases for file_io module."""

    def test_is_binary_empty_file(self, tmp_path):
        """Empty files should not be classified as binary."""
        f = tmp_path / "empty.dat"
        f.write_bytes(b"")
        assert FileUtils.is_binary(f) is False

    def test_is_binary_nonexistent(self, tmp_path):
        """Non-existent files should not crash."""
        f = tmp_path / "nonexistent.xyz"
        assert FileUtils.is_binary(f) is False

    def test_is_binary_known_text_extensions(self, tmp_path):
        """Known text extensions should short-circuit."""
        f = tmp_path / "test.py"
        f.write_bytes(b"\x00\x00\x00")
        assert FileUtils.is_binary(f) is False

    def test_read_text_smart_with_max_bytes(self, tmp_path):
        """read_text_smart should respect max_bytes."""
        f = tmp_path / "large.txt"
        f.write_text("A" * 10000, encoding="utf-8")
        content = FileUtils.read_text_smart(f, max_bytes=100)
        assert len(content) <= 200

    def test_get_metadata_nonexistent(self, tmp_path):
        """Metadata for nonexistent file should return defaults."""
        f = tmp_path / "nonexistent.txt"
        meta = FileUtils.get_metadata(f)
        assert "name" in meta
        assert meta["size"] == 0

    def test_get_language_tag_unknown(self):
        """Unknown extension returns empty string."""
        assert FileUtils.get_language_tag(".xyz123") == ""

    def test_should_ignore_git_spec(self, tmp_path):
        """Git spec matching for nested paths."""
        import pathspec

        spec = pathspec.PathSpec.from_lines("gitwildmatch", ["*.log", "build/"])
        assert FileUtils.should_ignore("error.log", pathlib.Path("error.log"), [], spec, False)
        assert FileUtils.should_ignore(
            "src", pathlib.Path("build/src"), [], spec, True
        )


class TestPathValidatorEdgeCases:
    """Edge cases for path validation."""

    def test_norm_path_with_dots(self):
        """Normalization resolves . and .. segments."""
        result = PathValidator.norm_path("/tmp/project/../src/./main.py")
        assert ".." not in result
        assert "/src/main.py" in result.lower() or "\\src\\main.py" in result.lower()

    def test_is_safe_same_path(self):
        """A path is safe against itself."""
        assert PathValidator.is_safe("/tmp/project", "/tmp/project") is True

    def test_is_safe_empty_root(self):
        """Empty root returns False."""
        assert PathValidator.is_safe("/some/path", "") is False

    def test_validate_project_root_drive(self, tmp_path):
        """Cannot register root drive as project."""
        if os.name != "nt":
            pytest.skip("Windows-specific test")
        with pytest.raises(PermissionError, match="system root"):
            PathValidator.validate_project("C:\\")


class TestFileOpsEdgeCases:
    """Edge cases for file operations."""

    def test_rename_rejects_traversal(self, tmp_path):
        """Rename should reject names with path separators."""
        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")
        with pytest.raises(ValueError, match="Path separators"):
            FileOps.rename_file(str(f), "../evil.txt")

    def test_create_rejects_dotdot(self, tmp_path):
        """Create should reject .. names."""
        with pytest.raises(ValueError, match="not allowed"):
            FileOps.create_item(str(tmp_path), "..", False)

    def test_delete_file_and_dir(self, tmp_path):
        """Delete works for both files and directories."""
        f = tmp_path / "file.txt"
        f.write_text("x", encoding="utf-8")
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "inner.txt").write_text("y", encoding="utf-8")

        assert FileOps.delete_file(str(f)) is True
        assert not f.exists()
        assert FileOps.delete_file(str(d)) is True
        assert not d.exists()

    def test_archive_preserves_structure(self, tmp_path):
        """Archive should preserve directory structure."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("print(1)", encoding="utf-8")
        out = tmp_path / "out.zip"
        FileOps.archive_selection([str(src / "main.py")], str(out), str(tmp_path))
        import zipfile

        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert any("main.py" in n for n in names)


class TestNoiseReducerEdgeCases:
    """Edge cases for noise reduction."""

    def test_clean_normal_lines(self):
        """Normal lines pass through."""
        result = NoiseReducer.clean("line 1\nline 2\nline 3")
        assert result == "line 1\nline 2\nline 3"

    def test_clean_truncates_long_lines(self):
        """Lines over 500 chars get truncated message."""
        long_line = "x" * 600
        result = NoiseReducer.clean(long_line)
        assert "skipped" in result

    def test_clean_detects_base64(self):
        """Base64-like content gets filtered or truncated."""
        import base64

        b64 = base64.b64encode(b"test data " * 50).decode()
        result = NoiseReducer.clean(b64)
        assert "skipped" in result


class TestFormatUtilsEdgeCases:
    """Additional format utils tests."""

    def test_collect_paths_absolute_mode(self, tmp_path):
        """Absolute mode returns full paths."""
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        result = FormatUtils.collect_paths([str(f)], mode="absolute")
        assert str(f) in result or str(f.resolve()) in result

    def test_estimate_tokens_cjk_heavy(self):
        """CJK text should have non-zero token estimates."""
        cjk = "你好世界" * 100
        cjk_tokens = FormatUtils.estimate_tokens(cjk)
        assert cjk_tokens > 0


class TestConfigEdgeCases:
    """Config module edge cases."""

    def test_update_custom_tools_rejects_non_dict(self, clean_config, mock_project):
        """update_custom_tools rejects non-dict input."""
        dm = clean_config
        p = str(mock_project)
        with pytest.raises(ValueError):
            dm.update_custom_tools(p, "string_not_dict")
        with pytest.raises(ValueError):
            dm.update_custom_tools(p, [1, 2])
        with pytest.raises(ValueError):
            dm.update_custom_tools(p, {123: "cmd"})

    def test_add_note_roundtrip(self, clean_config, mock_project):
        """Notes should survive save/load."""
        dm = clean_config
        p = str(mock_project)
        f = str(mock_project / "src" / "main.py")
        dm.add_note(p, f, "Refactor needed")
        proj = dm.get_project_data(p)
        norm_f = PathValidator.norm_path(f)
        assert proj["notes"].get(norm_f) == "Refactor needed"

    def test_add_and_remove_tag(self, clean_config, mock_project):
        """Tag add/remove lifecycle."""
        dm = clean_config
        p = str(mock_project)
        f = str(mock_project / "src" / "main.py")
        dm.add_tag(p, f, "Urgent")
        dm.add_tag(p, f, "Review")
        proj = dm.get_project_data(p)
        norm_f = PathValidator.norm_path(f)
        assert "Urgent" in proj["tags"][norm_f]
        assert "Review" in proj["tags"][norm_f]

        dm.remove_tag(p, f, "Urgent")
        proj = dm.get_project_data(p)
        assert "Urgent" not in proj["tags"][norm_f]
        assert "Review" in proj["tags"][norm_f]

    def test_resolve_project_root_empty(self, clean_config):
        """Empty path returns None."""
        assert clean_config.resolve_project_root("") is None

    def test_recent_projects_cap(self, clean_config, tmp_path):
        """Recent projects list should be capped at 15."""
        dm = clean_config
        for i in range(20):
            p = tmp_path / f"proj_{i}"
            p.mkdir(exist_ok=True)
            dm.add_to_recent(str(p))
        assert len(dm.data["recent_projects"]) <= 15
