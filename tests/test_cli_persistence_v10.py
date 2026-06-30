"""Regression tests for CLI (fctx.py) staging/categorize persistence.

Background
----------
A review found silent data loss in ``fctx.py``: ``cmd_stage`` and
``cmd_categorize`` previously called ``DataManager.get_project_data()``, which
returns a disconnected ``model_dump()`` *snapshot* dict. Mutating that snapshot
(``snapshot["staging_list"].append(...)`` / ``snapshot["staging_list"] = []``)
had no effect on the real ``ProjectConfig`` model, so the subsequent
``data_mgr.save()`` persisted the *unchanged* config:

* ``fctx stage <proj> <file>``  -> file silently NOT staged
* ``fctx categorize <proj> <cat>`` -> files moved on disk, but the real
  staging list silently NOT cleared

The fix switches both mutating handlers to ``get_project_data_obj()`` (the live
``ProjectConfig``). These tests prove persistence against the real DataManager
model AND against a fresh reload from disk.
"""

from unittest.mock import patch

from file_cortex_core import DataManager, PathValidator

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _run_cli(argv):
    """Invoke ``fctx.main`` with a synthetic argv (matches existing CLI tests)."""
    from fctx import main as cli_main

    with patch("sys.argv", argv):
        cli_main()


def _register_project(dm, project_path):
    """Ensure a project is present in config.projects.

    The CLI's _resolve_project guards on DataManager.resolve_project_root(),
    so tests must register the project before invoking fctx commands.
    """
    dm.add_to_recent(str(project_path))
    dm.get_project_data_obj(str(project_path))


# ============================================================================
# DataManager snapshot isolation (documents the root cause)
# ============================================================================


class TestSnapshotIsolationRootCause:
    """Locks in WHY the CLI must use get_project_data_obj(), not the snapshot.

    get_project_data() returns model_dump(): a disconnected dict. Mutating it
    must NOT touch the live model or be persisted by save().
    """

    def test_get_project_data_returns_disconnected_snapshot(self, clean_config, mock_project):
        """Mutating the get_project_data() snapshot must not affect the model."""
        dm = clean_config
        proj_path = str(mock_project)

        snapshot = dm.get_project_data(proj_path)
        snapshot["staging_list"].append("ghost_file.py")
        snapshot["staging_list"] = ["another.py"]
        dm.save()

        # The live model is untouched by the snapshot mutation.
        live = dm.get_project_data_obj(proj_path)
        assert live.staging_list == []
        assert "ghost_file.py" not in dm.get_project_data(proj_path)["staging_list"]

    def test_get_project_data_obj_is_live_reference(self, clean_config, mock_project):
        """Mutating the ProjectConfig object IS persisted by save()."""
        dm = clean_config
        proj_path = str(mock_project)

        live = dm.get_project_data_obj(proj_path)
        live.staging_list.append("real_file.py")
        dm.save()

        assert dm.get_project_data_obj(proj_path).staging_list == ["real_file.py"]


# ============================================================================
# fctx stage persistence
# ============================================================================


class TestCLIStagePersists:
    """``fctx stage`` must persist staged files to the real ProjectConfig."""

    def test_stage_persists_to_live_model(self, clean_config, mock_project, capsys):
        """Staged file appears on the live ProjectConfig.staging_list."""
        dm = clean_config
        _register_project(dm, mock_project)
        test_file = mock_project / "stage_me.py"
        test_file.write_text("x = 1", encoding="utf-8")

        _run_cli(["fctx", "stage", str(mock_project), str(test_file)])

        captured = capsys.readouterr()
        assert "Staged:" in captured.out

        live = dm.get_project_data_obj(str(mock_project))
        norm_expected = PathValidator.norm_path(str(test_file))
        assert norm_expected in live.staging_list

    def test_stage_persists_to_disk_on_reload(self, clean_config, mock_project):
        """Staged file survives a fresh DataManager reload from disk."""
        dm = clean_config
        config_path = clean_config.config_path
        _register_project(dm, mock_project)
        test_file = mock_project / "reload_me.py"
        test_file.write_text("y = 2", encoding="utf-8")

        _run_cli(["fctx", "stage", str(mock_project), str(test_file)])

        # Force a brand-new instance that re-reads the on-disk config.
        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            reloaded = DataManager()
            staged = reloaded.get_project_data_obj(str(mock_project)).staging_list

        norm_expected = PathValidator.norm_path(str(test_file))
        assert norm_expected in staged, (
            "staged file was not persisted to disk (silent data loss)"
        )

    def test_stage_already_staged_is_idempotent(self, clean_config, mock_project, capsys):
        """Staging the same file twice does not duplicate the entry."""
        dm = clean_config
        _register_project(dm, mock_project)
        test_file = mock_project / "dup.py"
        test_file.write_text("z = 3", encoding="utf-8")

        _run_cli(["fctx", "stage", str(mock_project), str(test_file)])
        _run_cli(["fctx", "stage", str(mock_project), str(test_file)])

        out = capsys.readouterr().out
        assert "Already staged" in out
        live = dm.get_project_data_obj(str(mock_project))
        norm_expected = PathValidator.norm_path(str(test_file))
        assert live.staging_list.count(norm_expected) == 1

    def test_stage_unsafe_path_not_persisted(self, clean_config, mock_project, tmp_path, capsys):
        """A path outside the project root is rejected and never persisted."""
        dm = clean_config
        _register_project(dm, mock_project)
        outside = tmp_path / "outside_proj" / "evil.py"
        outside.parent.mkdir(parents=True)
        outside.write_text("bad", encoding="utf-8")

        _run_cli(["fctx", "stage", str(mock_project), str(outside)])

        out = capsys.readouterr().out
        assert "ERROR" in out or "unsafe" in out.lower()
        assert dm.get_project_data_obj(str(mock_project)).staging_list == []


# ============================================================================
# fctx categorize persistence
# ============================================================================


class TestCLICategorizeClearsStaging:
    """``fctx categorize`` must move files AND clear the real staging list."""

    def test_categorize_clears_live_staging_list(self, clean_config, mock_project, capsys):
        """After categorize, the live ProjectConfig.staging_list is empty."""
        dm = clean_config
        _register_project(dm, mock_project)

        target = mock_project / "src" / "main.py"
        assert target.exists()  # provided by mock_project fixture
        dm.batch_stage(str(mock_project), [str(target)])
        assert dm.get_project_data_obj(str(mock_project)).staging_list, (
            "precondition: staging list must be populated"
        )

        _run_cli(["fctx", "categorize", str(mock_project), "Scripts"])

        out = capsys.readouterr().out
        assert "Moved" in out
        # The critical regression assertion: real list cleared.
        assert dm.get_project_data_obj(str(mock_project)).staging_list == [], (
            "staging list was not cleared on the live model (silent data loss)"
        )

    def test_categorize_clear_persists_to_disk_on_reload(self, clean_config, mock_project):
        """Staging list stays empty after a fresh DataManager reload."""
        dm = clean_config
        config_path = clean_config.config_path
        _register_project(dm, mock_project)

        target = mock_project / "src" / "utils.js"
        assert target.exists()
        dm.batch_stage(str(mock_project), [str(target)])
        assert dm.get_project_data_obj(str(mock_project)).staging_list

        _run_cli(["fctx", "categorize", str(mock_project), "Scripts"])

        with patch("file_cortex_core.config._CONFIG_FILE", config_path):
            DataManager.reset()
            reloaded = DataManager()
            staged = reloaded.get_project_data_obj(str(mock_project)).staging_list

        assert staged == [], (
            "staging list was not cleared on disk (silent data loss on reload)"
        )

    def test_categorize_empty_staging_prints_message(self, clean_config, mock_project, capsys):
        """Categorize with an empty staging list is a no-op with a clear message."""
        dm = clean_config
        _register_project(dm, mock_project)
        assert dm.get_project_data_obj(str(mock_project)).staging_list == []

        _run_cli(["fctx", "categorize", str(mock_project), "Scripts"])

        out = capsys.readouterr().out
        assert "Staging list is empty." in out

    def test_categorize_unknown_category_errors_and_keeps_list(
        self, clean_config, mock_project, capsys
    ):
        """An unknown category raises an error and does NOT clear the list."""
        dm = clean_config
        _register_project(dm, mock_project)

        target = mock_project / "src" / "main.py"
        dm.batch_stage(str(mock_project), [str(target)])
        before = list(dm.get_project_data_obj(str(mock_project)).staging_list)

        _run_cli(["fctx", "categorize", str(mock_project), "NoSuchCategory"])

        out = capsys.readouterr().out
        assert "ERROR" in out
        # On failure, staging list must be preserved (not silently wiped).
        assert dm.get_project_data_obj(str(mock_project)).staging_list == before


# ============================================================================
# Full stage -> categorize round trip
# ============================================================================


class TestStageCategorizeRoundTrip:
    """End-to-end persistence across stage then categorize."""

    def test_stage_then_categorize_round_trip(self, clean_config, mock_project, capsys):
        """Stage via CLI, then categorize via CLI: list populated then cleared."""
        dm = clean_config
        _register_project(dm, mock_project)

        f1 = mock_project / "round_a.py"
        f2 = mock_project / "round_b.py"
        f1.write_text("a = 1", encoding="utf-8")
        f2.write_text("b = 2", encoding="utf-8")

        _run_cli(["fctx", "stage", str(mock_project), str(f1)])
        _run_cli(["fctx", "stage", str(mock_project), str(f2)])

        live = dm.get_project_data_obj(str(mock_project))
        assert len(live.staging_list) == 2

        _run_cli(["fctx", "categorize", str(mock_project), "Scripts"])

        assert dm.get_project_data_obj(str(mock_project)).staging_list == []
        assert "Moved 2 files" in capsys.readouterr().out


# ============================================================================
# fctx run legacy config fallback
# ============================================================================


class TestCLIRunLegacyConfigFallback:
    """``fctx run`` must tolerate legacy configs missing custom_tools."""

    def test_run_missing_custom_tools_prints_not_found(
        self, clean_config, mock_project, monkeypatch, capsys
    ):
        """Missing custom_tools should use the normal not-found path."""
        dm = clean_config
        _register_project(dm, mock_project)

        def _legacy_project_data(self, path_str):
            return {"staging_list": []}

        monkeypatch.setattr(DataManager, "get_project_data", _legacy_project_data)

        _run_cli(["fctx", "run", str(mock_project), "Summary"])

        assert "Tool 'Summary' not found." in capsys.readouterr().out


# ============================================================================
# fctx copy
# ============================================================================


class TestCLICopy:
    """``fctx copy`` must respect the security boundary and report results."""

    def test_copy_file_success(self, clean_config, mock_project, capsys):
        """Copying a file via CLI prints the destination path."""
        dm = clean_config
        _register_project(dm, mock_project)
        src = mock_project / "README.md"
        dst_dir = mock_project / "src"

        _run_cli(["fctx", "copy", str(mock_project), str(src), str(dst_dir)])

        out = capsys.readouterr().out
        assert "Copied:" in out
        assert (dst_dir / "README.md").exists()

    def test_copy_unsafe_source_blocked(self, clean_config, mock_project, tmp_path, capsys):
        """A source outside the project root is rejected."""
        dm = clean_config
        _register_project(dm, mock_project)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")

        _run_cli(["fctx", "copy", str(mock_project), str(outside), str(mock_project / "src")])

        out = capsys.readouterr().out
        assert "ERROR" in out
        assert not (mock_project / "src" / "outside.txt").exists()

    def test_copy_unsafe_destination_blocked(
        self, clean_config, mock_project, tmp_path, capsys
    ):
        """A destination outside the project root is rejected."""
        dm = clean_config
        _register_project(dm, mock_project)
        outside_dir = tmp_path / "escape"
        outside_dir.mkdir()

        _run_cli([
            "fctx", "copy", str(mock_project),
            str(mock_project / "README.md"), str(outside_dir),
        ])

        out = capsys.readouterr().out
        assert "ERROR" in out

    def test_copy_missing_source_prints_error(self, clean_config, mock_project, capsys):
        """A non-existent source prints an error and does nothing."""
        dm = clean_config
        _register_project(dm, mock_project)
        missing = mock_project / "missing.txt"

        _run_cli(["fctx", "copy", str(mock_project), str(missing), str(mock_project / "src")])

        out = capsys.readouterr().out
        assert "ERROR" in out

    def test_batch_copy_cli(self, clean_config, mock_project, capsys):
        """``fctx copy`` with multiple sources reports each copied path."""
        dm = clean_config
        _register_project(dm, mock_project)
        src1 = mock_project / "src" / "main.py"
        src2 = mock_project / "src" / "utils.js"
        dst = mock_project / "batch_cli_out"
        dst.mkdir()

        _run_cli([
            "fctx", "copy", str(mock_project),
            str(src1), str(src2), str(dst),
        ])

        out = capsys.readouterr().out
        # Both sources must be reported as copied.
        assert out.count("Copied:") == 2
        assert (dst / "main.py").exists()
        assert (dst / "utils.js").exists()

    def test_copy_cli_single_source_still_works(self, clean_config, mock_project, capsys):
        """``fctx copy`` with a single source still works (backward compatible)."""
        dm = clean_config
        _register_project(dm, mock_project)
        src = mock_project / "config.json"
        dst = mock_project / "single_cli_out"
        dst.mkdir()

        _run_cli(["fctx", "copy", str(mock_project), str(src), str(dst)])

        out = capsys.readouterr().out
        assert "Copied:" in out
        assert (dst / "config.json").exists()


# ============================================================================
# fctx extract
# ============================================================================


class TestCLIExtract:
    """``fctx extract`` must respect the security boundary and report results."""

    def _make_zip(self, members, path):
        """Helper to create a ZIP archive."""
        import zipfile
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, payload in members.items():
                zf.writestr(name, payload)
        return path

    def test_extract_archive_success(self, clean_config, mock_project, tmp_path, capsys):
        """Extracting a benign archive via CLI prints the entry count."""
        dm = clean_config
        _register_project(dm, mock_project)
        archive = self._make_zip(
            {"a.txt": b"alpha", "b.txt": b"beta"},
            tmp_path / "bundle.zip",
        )
        dst = mock_project / "extracted"

        _run_cli(["fctx", "extract", str(mock_project), str(archive), str(dst)])

        out = capsys.readouterr().out
        assert "Extracted" in out
        assert (dst / "a.txt").read_bytes() == b"alpha"

    def test_extract_unsafe_destination_blocked(
        self, clean_config, mock_project, tmp_path, capsys
    ):
        """A destination outside the project root is rejected."""
        dm = clean_config
        _register_project(dm, mock_project)
        archive = self._make_zip({"a.txt": b"a"}, tmp_path / "ok.zip")
        outside = tmp_path / "escape"
        outside.mkdir()

        _run_cli(["fctx", "extract", str(mock_project), str(archive), str(outside)])

        out = capsys.readouterr().out
        assert "ERROR" in out

    def test_extract_missing_archive_prints_error(self, clean_config, mock_project, capsys):
        """A non-existent archive prints an error."""
        dm = clean_config
        _register_project(dm, mock_project)
        missing = mock_project / "missing.zip"

        _run_cli(["fctx", "extract", str(mock_project), str(missing), str(mock_project / "out")])

        out = capsys.readouterr().out
        assert "ERROR" in out
