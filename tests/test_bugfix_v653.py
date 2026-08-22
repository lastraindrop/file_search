"""Regression tests for the v6.5.3 review-driven bugfix round (B1-B13).

Each test class documents the bug it guards:
- Windows config-lock liveness probe must not use ``os.kill(pid, 0)`` (B1).
- Path-collection presets must read Pydantic models, not only dicts (B2).
- A corrupt on-disk config must not brick every later save (B3).
- Null fields in global settings must be ignored, not 500 (B7).
- Case-only renames must work on case-insensitive filesystems (B6).
- Directory-only gitignore rules must hide directories in the tree (B8).
- Exclude patterns must be case-faithful on POSIX (B9).
- ZIP archive members must use forward-slash names (B13).
"""

import json
import os
import pathlib
import subprocess
import sys
import zipfile
from unittest.mock import patch

from file_cortex_core.actions import FileOps
from file_cortex_core.config import (
    CollectionProfile,
    DataManager,
    _is_process_alive,
)
from file_cortex_core.file_io import FileUtils


class TestWindowsSafeLockProbe:
    """B1: the config-lock liveness probe must be safe on Windows."""

    def test_process_alive_current_pid(self) -> None:
        """The current process must always be reported alive."""
        assert _is_process_alive(os.getpid()) is True

    def test_process_alive_invalid_pid(self) -> None:
        """A clearly invalid PID must be reported dead."""
        assert _is_process_alive(2**22) is False

    def test_process_alive_terminated_child(self) -> None:
        """A terminated child process must be reported dead."""
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            child.terminate()
            child.wait(timeout=10)
            assert _is_process_alive(child.pid) is False
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


class TestPathCollectionPresetCompat:
    """B2: preset profiles may arrive as dicts OR Pydantic models."""

    def test_profile_value_reads_dict_and_model(self) -> None:
        """_profile_value must read from both plain dicts and CollectionProfile."""
        from file_cortex_core.gui.path_collection import _profile_value

        assert _profile_value({"prefix": "file:", "sep": " "}, "prefix") == "file:"
        assert _profile_value({"prefix": "file:"}, "suffix", "dflt") == "dflt"

        prof = CollectionProfile(prefix="@", suffix="/", sep="\\n")
        assert _profile_value(prof, "prefix") == "@"
        assert _profile_value(prof, "suffix") == "/"
        assert _profile_value(prof, "sep") == "\\n"
        assert _profile_value(prof, "missing", "dflt") == "dflt"


class TestCorruptConfigSelfHeal:
    """B3: invalid on-disk config must not permanently brick saves."""

    def test_save_rewrites_invalid_disk_config(self, tmp_path) -> None:
        """A save after a corrupt config must succeed and heal the file."""
        cfg = tmp_path / "config.json"
        cfg.write_text('{"global_settings": {"token_threshold": 0}}', encoding="utf-8")
        with patch("file_cortex_core.config._CONFIG_FILE", cfg):
            DataManager.reset()
            dm = DataManager()
            dm.add_to_recent(str(tmp_path))  # triggers save(); must not raise
            reloaded = json.loads(cfg.read_text(encoding="utf-8"))
            assert reloaded["global_settings"]["token_threshold"] >= 1
        DataManager.reset()


class TestGlobalSettingsNullTolerance:
    """B7: explicit nulls on optional setting fields are 'leave unchanged'."""

    def test_null_fields_ignored(self, api_client) -> None:
        """POSTing null for numeric fields must 200 and leave defaults intact."""
        res = api_client.post(
            "/api/global/settings",
            json={"preview_limit_mb": None, "token_ratio": None, "theme": "light"},
        )
        assert res.status_code == 200
        settings = api_client.get("/api/global/settings").json()
        assert settings["theme"] == "light"
        assert settings["preview_limit_mb"] == 1.0
        assert settings["token_ratio"] == 4.0


class TestCaseOnlyRename:
    """B6: case-only renames must not be treated as conflicts."""

    def test_rename_file_case_only(self, tmp_path) -> None:
        """rename_file('a.txt' -> 'A.txt') must succeed on every platform."""
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        new = FileOps.rename_file(str(f), "A.txt")
        assert pathlib.Path(new).name == "A.txt"
        assert pathlib.Path(new).exists()
        # On case-insensitive filesystems (Windows/macOS) the old name still
        # resolves to the renamed file, so compare exact directory entries.
        names = os.listdir(tmp_path)
        assert "A.txt" in names
        assert "a.txt" not in names

    def test_batch_rename_case_only_no_suffix(self, tmp_path) -> None:
        """batch_rename must not fall back to a suffixed target for case."""
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        results = FileOps.batch_rename(str(tmp_path), [str(f)], "a", "A", dry_run=True)
        assert results[0]["status"] == "ok"
        assert str(results[0]["new"]).endswith("A.txt")


class TestChildrenGitignoreDirRules:
    """B8: directory-only gitignore rules must hide directories in the tree."""

    def test_children_hides_gitignored_dirs(self, api_client, tmp_path) -> None:
        """A 'build/' gitignore rule must remove the directory from children."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "build").mkdir()
        (proj / "build" / "app.js").write_text("x", encoding="utf-8")
        (proj / "src").mkdir()
        (proj / "src" / "main.py").write_text("print(1)", encoding="utf-8")
        (proj / ".gitignore").write_text("build/\n", encoding="utf-8")

        res_open = api_client.post("/api/open", json={"path": str(proj)})
        assert res_open.status_code == 200
        res = api_client.post("/api/fs/children", json={"path": str(proj)})
        assert res.status_code == 200
        names = [c["name"] for c in res.json()["children"]]
        assert "build" not in names
        assert "src" in names


class TestExcludeCaseHandling:
    """B9: exclude patterns must be case-faithful on POSIX."""

    def test_mixed_case_pattern_matches_on_all_platforms(self, tmp_path) -> None:
        """'.DS_Store' (mixed case) must exclude '.DS_Store' everywhere."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".DS_Store").write_text("meta", encoding="utf-8")
        (proj / "keep.txt").write_text("keep", encoding="utf-8")
        results = list(FileUtils.walk_filtered(proj, [".DS_Store"], None))
        paths = [str(r[1]) for r in results]
        assert not any(".DS_Store" in p for p in paths)
        assert any("keep.txt" in p for p in paths)

    def test_posix_case_sensitive_patterns(self, tmp_path) -> None:
        """POSIX keeps case-sensitive exclude semantics; Windows is insensitive."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "Report.TXT").write_text("x", encoding="utf-8")
        results = list(FileUtils.walk_filtered(proj, ["*.txt"], None))
        if os.name == "nt":
            assert len(results) == 0
        else:
            assert len(results) == 1


class TestArchiveArcnames:
    """B13: ZIP members must use forward-slash names on every platform."""

    def test_archive_uses_forward_slashes(self, tmp_path) -> None:
        """Archive names must never contain backslashes."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "sub").mkdir()
        (proj / "sub" / "file.txt").write_text("x", encoding="utf-8")
        out = tmp_path / "out.zip"
        FileOps.archive_selection([str(proj / "sub")], str(out), str(proj))
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert names
        assert all("\\" not in n for n in names)
