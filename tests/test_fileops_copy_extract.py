"""Focused core tests for FileOps.copy_item and FileOps.extract_archive.

Covers:
  * Copy of files and directories (metadata preservation where reasonable).
  * Destination conflict handling (no overwrite by default).
  * Security boundary enforcement (unsafe source / destination).
  * Normal and nested ZIP extraction.
  * Zip-slip / path-escape payloads (``..``, absolute, drive, UNC, backslash).
"""

import pathlib
import zipfile

import pytest

from file_cortex_core import FileOps

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _make_zip(members: dict[str, bytes | None], path: pathlib.Path) -> pathlib.Path:
    """Creates a ZIP archive at *path*.

    Args:
        members: Mapping of member filename -> payload bytes. A ``None`` payload
            marks a directory entry (name should end with ``/``).
        path: Output archive path.

    Returns:
        The created archive path.
    """
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            if payload is None:
                # Directory entry.
                zi = zipfile.ZipInfo(name)
                zi.external_attr = (0o040000 << 16) | 0o755
                zf.writestr(zi, b"")
            else:
                zf.writestr(name, payload)
    return path


# =============================================================================
# copy_item
# =============================================================================

class TestCopyItem:
    """Tests for FileOps.copy_item."""

    def test_copy_file_creates_copy_and_preserves_content(self, mock_project):
        """Copying a file duplicates its content at the destination."""
        src = mock_project / "README.md"
        dst_dir = mock_project / "src"
        # Ensure distinct content to detect a stale overwrite.
        src.write_text("copy me", encoding="utf-8")

        result = FileOps.copy_item([str(src)], str(dst_dir), str(mock_project))

        assert pathlib.Path(result[0]) == dst_dir / "README.md"
        assert (dst_dir / "README.md").read_text(encoding="utf-8") == "copy me"
        # Source is untouched.
        assert src.read_text(encoding="utf-8") == "copy me"

    def test_copy_file_preserves_metadata(self, mock_project):
        """shutil.copy2 should preserve mtime (metadata)."""
        src = mock_project / "README.md"
        src.write_text("meta", encoding="utf-8")
        dst_dir = mock_project / "src"

        FileOps.copy_item([str(src)], str(dst_dir), str(mock_project))

        copied = dst_dir / "README.md"
        assert copied.exists()
        # copy2 copies metadata; allow tiny FS rounding tolerance.
        assert int(copied.stat().st_mtime) == int(src.stat().st_mtime)

    def test_copy_directory_recursively(self, mock_project):
        """Copying a directory copies its full subtree."""
        src = mock_project / "src"

        # Use a dedicated target dir to avoid name collision with existing src.
        target = mock_project / "backup"
        target.mkdir()

        result = FileOps.copy_item([str(src)], str(target), str(mock_project))

        copy_root = pathlib.Path(result[0])
        assert copy_root == target / "src"
        assert (copy_root / "main.py").exists()
        assert (copy_root / "utils.js").exists()
        # Originals remain.
        assert (src / "main.py").exists()

    def test_copy_conflict_raises_file_exists_error(self, mock_project):
        """A name collision at the destination must not overwrite."""
        src = mock_project / "README.md"
        src.write_text("SRC", encoding="utf-8")
        # Create a collision: same name lives under src/.
        (mock_project / "src" / "README.md").write_text("DST", encoding="utf-8")

        with pytest.raises(FileExistsError):
            FileOps.copy_item(
                [str(src)], str(mock_project / "src"), str(mock_project)
            )

        # Destination is unchanged (no overwrite).
        assert (mock_project / "src" / "README.md").read_text(encoding="utf-8") == "DST"

    def test_copy_missing_source_raises(self, mock_project):
        """A non-existent source raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            FileOps.copy_item(
                str(mock_project / "nope.txt"),
                str(mock_project / "src"),
                str(mock_project),
            )

    def test_copy_missing_destination_dir_raises(self, mock_project):
        """A non-existent destination directory raises FileNotFoundError."""
        src = mock_project / "README.md"
        with pytest.raises(FileNotFoundError):
            FileOps.copy_item(
                str(src),
                str(mock_project / "does_not_exist"),
                str(mock_project),
            )

    def test_copy_source_outside_root_rejected(self, tmp_path, mock_project):
        """Source outside the project root is blocked by the security boundary."""
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")

        with pytest.raises(PermissionError):
            FileOps.copy_item(
                [str(outside)], str(mock_project / "src"), str(mock_project)
            )

    def test_copy_destination_outside_root_rejected(self, mock_project, tmp_path):
        """Destination outside the project root is blocked."""
        src = mock_project / "README.md"
        outside_dir = tmp_path / "escape"
        outside_dir.mkdir()

        with pytest.raises(PermissionError):
            FileOps.copy_item([str(src)], str(outside_dir), str(mock_project))

    def test_copy_directory_into_descendant_rejected(self, mock_project):
        """Copying a directory into its own descendant must not recurse."""
        parent = mock_project / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()
        (parent / "file.txt").write_text("x", encoding="utf-8")

        with pytest.raises((ValueError, FileExistsError, OSError)):
            FileOps.copy_item([str(parent)], str(child), str(mock_project))

    def test_copy_conflict_with_existing_directory_rejected(self, mock_project):
        """Copying a file when a directory with the same name exists raises."""
        src = mock_project / "README.md"
        src.write_text("SRC", encoding="utf-8")
        dst_dir = mock_project / "src"
        # "src" already exists as a directory; copying README.md into root
        # with dst_dir == root and src.name == "README.md" would collide
        # only if README.md exists.  Instead create a directory named README.md
        # inside src/ so that copying README.md into src/ collides with the dir.
        (dst_dir / "README.md").mkdir()

        with pytest.raises(FileExistsError):
            FileOps.copy_item([str(src)], str(dst_dir), str(mock_project))

    def test_batch_copy_multiple_files(self, mock_project):
        """Copying several files in one call places every one at the dst."""
        srcs = [
            str(mock_project / "src" / "main.py"),
            str(mock_project / "src" / "utils.js"),
            str(mock_project / "README.md"),
        ]
        dst = mock_project / "batch_out"
        dst.mkdir()
        originals = {
            "main.py": (mock_project / "src" / "main.py").read_text(
                encoding="utf-8"
            ),
            "utils.js": (mock_project / "src" / "utils.js").read_text(
                encoding="utf-8"
            ),
            "README.md": (mock_project / "README.md").read_text(
                encoding="utf-8"
            ),
        }

        result = FileOps.copy_item(srcs, str(dst), str(mock_project))

        assert len(result) == 3
        names = {pathlib.Path(p).name for p in result}
        assert names == {"main.py", "utils.js", "README.md"}
        for name, content in originals.items():
            copied = dst / name
            assert copied.exists()
            assert copied.read_text(encoding="utf-8") == content
        # Sources are untouched.
        assert (mock_project / "src" / "main.py").exists()

    def test_batch_copy_mixed_files_and_dirs(self, mock_project):
        """A batch may mix a single file and a whole directory."""
        file_src = str(mock_project / "src" / "main.py")
        dir_src = str(mock_project / "src")
        dst = mock_project / "mixed_out"
        dst.mkdir()

        result = FileOps.copy_item([file_src, dir_src], str(dst), str(mock_project))

        assert len(result) == 2
        # The file copy lands at dst/main.py.
        assert (dst / "main.py").exists()
        # The directory copy lands at dst/src/ with its full subtree.
        assert (dst / "src").is_dir()
        assert (dst / "src" / "main.py").exists()
        assert (dst / "src" / "utils.js").exists()

    def test_batch_copy_single_item_still_works(self, mock_project):
        """A single-element source list behaves like the legacy single copy."""
        src = mock_project / "README.md"
        src.write_text("solo", encoding="utf-8")
        dst = mock_project / "solo_out"
        dst.mkdir()

        result = FileOps.copy_item([str(src)], str(dst), str(mock_project))

        assert len(result) == 1
        assert pathlib.Path(result[0]) == dst / "README.md"
        assert (dst / "README.md").read_text(encoding="utf-8") == "solo"

    def test_batch_copy_conflict_aborts_all(self, mock_project):
        """A conflict on the leading item aborts before later items are written."""
        # The conflicting source is placed first so it raises immediately; the
        # second source must NOT be partially copied.
        src_conflict = mock_project / "src" / "main.py"
        src_other = mock_project / "src" / "utils.js"
        dst = mock_project / "conflict_out"
        dst.mkdir()
        (dst / "main.py").write_text("BLOCKER", encoding="utf-8")

        with pytest.raises(FileExistsError):
            FileOps.copy_item(
                [str(src_conflict), str(src_other)],
                str(dst),
                str(mock_project),
            )

        # Critical invariant: no partial write of the later item.
        assert not (dst / "utils.js").exists()
        # The pre-existing blocker is untouched.
        assert (dst / "main.py").read_text(encoding="utf-8") == "BLOCKER"

    def test_progress_tracker_new_and_get(self):
        """ProgressTracker lifecycle: new, update, get, and unknown -> None."""
        from file_cortex_core.actions import ProgressTracker

        task_id = ProgressTracker.new_task(total=3)
        assert isinstance(task_id, str) and task_id

        state = ProgressTracker.get(task_id)
        assert state is not None
        assert state["task_id"] == task_id
        assert state["total"] == 3
        assert state["done"] == 0
        assert state["status"] == "pending"

        ProgressTracker.update(task_id, done=1, status="running", message="one")
        state = ProgressTracker.get(task_id)
        assert state["done"] == 1
        assert state["status"] == "running"
        assert state["message"] == "one"

        # An unknown task_id resolves to None.
        assert ProgressTracker.get("definitely-unknown-task-id-xyz") is None


# =============================================================================
# extract_archive
# =============================================================================

class TestExtractArchive:
    """Tests for FileOps.extract_archive."""

    def test_extract_normal_archive(self, mock_project, tmp_path):
        """A benign archive extracts all members into the destination."""
        archive = _make_zip(
            {"a.txt": b"alpha", "b.txt": b"beta"},
            tmp_path / "normal.zip",
        )
        dst = mock_project / "extracted"

        result = FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        assert dst.is_dir()
        assert (dst / "a.txt").read_bytes() == b"alpha"
        assert (dst / "b.txt").read_bytes() == b"beta"
        # All member paths are returned.
        names = {pathlib.Path(p).name for p in result}
        assert {"a.txt", "b.txt"} <= names

    def test_extract_nested_directories(self, mock_project, tmp_path):
        """Nested member paths create the intermediate directories."""
        archive = _make_zip(
            {"top/sub/deep.txt": b"deep"}, tmp_path / "nested.zip"
        )
        dst = mock_project / "out"

        result = FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        assert (dst / "top" / "sub" / "deep.txt").read_bytes() == b"deep"
        assert any(p.endswith("deep.txt") for p in result)

    def test_extract_auto_creates_destination(self, mock_project, tmp_path):
        """A missing destination directory is created (with parents)."""
        archive = _make_zip({"x.txt": b"x"}, tmp_path / "auto.zip")
        dst = mock_project / "new" / "nested" / "dir"

        assert not dst.exists()
        FileOps.extract_archive(str(archive), str(dst), str(mock_project))
        assert dst.is_dir()
        assert (dst / "x.txt").exists()

    def test_extract_empty_archive(self, mock_project, tmp_path):
        """An empty archive extracts nothing but creates the destination."""
        archive = _make_zip({}, tmp_path / "empty.zip")
        dst = mock_project / "empty_out"

        result = FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        assert dst.is_dir()
        assert result == []

    def test_extract_existing_target_rejected_without_overwrite(
        self, mock_project, tmp_path
    ):
        """Extraction must not overwrite existing files by default."""
        archive = _make_zip({"a.txt": b"new"}, tmp_path / "conflict.zip")
        dst = mock_project / "out"
        dst.mkdir()
        existing = dst / "a.txt"
        existing.write_text("old", encoding="utf-8")

        with pytest.raises(FileExistsError):
            FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        assert existing.read_text(encoding="utf-8") == "old"

    def test_extract_missing_archive_raises(self, mock_project):
        """A non-existent archive raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            FileOps.extract_archive(
                str(mock_project / "missing.zip"),
                str(mock_project / "out"),
                str(mock_project),
            )

    def test_extract_non_zip_raises(self, mock_project):
        """A non-ZIP file is rejected with ValueError."""
        fake = mock_project / "not_a_zip.txt"
        fake.write_text("plain text", encoding="utf-8")

        with pytest.raises(ValueError):
            FileOps.extract_archive(
                str(fake), str(mock_project / "out"), str(mock_project)
            )

    def test_extract_archive_outside_root_allowed_when_dst_safe(
        self, tmp_path, mock_project
    ):
        """An archive living outside the project can be extracted when dst is safe.

        Extraction imports external bundles into a project; the security
        boundary is the *destination* (where members land), not the archive
        source. A valid archive with benign members must extract normally.
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        archive = _make_zip({"a.txt": b"a"}, outside / "bundle.zip")

        result = FileOps.extract_archive(
            str(archive), str(mock_project / "out"), str(mock_project)
        )

        assert (mock_project / "out" / "a.txt").read_bytes() == b"a"
        assert any(p.endswith("a.txt") for p in result)

    def test_extract_destination_outside_root_rejected(self, mock_project, tmp_path):
        """An extraction destination outside the project root is blocked."""
        archive = _make_zip({"a.txt": b"a"}, mock_project / "ok.zip")
        outside = tmp_path / "escape"
        outside.mkdir()

        with pytest.raises(PermissionError):
            FileOps.extract_archive(str(archive), str(outside), str(mock_project))

    def test_extract_with_progress(self, mock_project, tmp_path):
        """Extracting with a task_id tracks progress through to 'done'."""
        from file_cortex_core.actions import ProgressTracker

        archive = _make_zip(
            {"a.txt": b"alpha", "b.txt": b"beta"},
            tmp_path / "progress.zip",
        )
        dst = mock_project / "prog_out"
        task_id = ProgressTracker.new_task(total=2)

        result = FileOps.extract_archive(
            str(archive), str(dst), str(mock_project), task_id=task_id
        )

        assert len(result) >= 2
        assert (dst / "a.txt").read_bytes() == b"alpha"
        state = ProgressTracker.get(task_id)
        assert state is not None
        assert state["status"] == "done"
        assert state["done"] == state["total"]

    def test_extract_transactional_no_partial_write(self, mock_project, tmp_path):
        """A mixed safe/traversal archive extracts nothing and leaks no staging dir.

        The first member is benign and the second is a path-traversal payload.
        Pass-1 validation rejects the whole archive before any bytes are
        written, so even the safe member never lands on disk and no temporary
        staging directory is left behind.
        """
        archive = _make_zip(
            {"safe.txt": b"safe", "../evil.txt": b"pwned"},
            tmp_path / "mixed_partial.zip",
        )
        dst = mock_project / "partial_target"

        with pytest.raises(ValueError):
            FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        # No file extracted at all (atomicity).
        assert not (dst / "safe.txt").exists()
        assert not list(mock_project.parent.rglob("evil.txt"))
        # No staging temp directory leaked next to the destination.
        leaked = [
            p
            for p in dst.parent.iterdir()
            if p.is_dir() and p.name.startswith(".fctx_extract_")
        ]
        assert leaked == []

    def test_extract_transactional_staging_cleanup_on_failure(
        self, mock_project, tmp_path
    ):
        """A conflicting target raises and removes the staging directory."""
        archive = _make_zip({"a.txt": b"new"}, tmp_path / "conflict.zip")
        dst = mock_project / "conflict_out"
        dst.mkdir()
        existing = dst / "a.txt"
        existing.write_text("old", encoding="utf-8")

        with pytest.raises(FileExistsError):
            FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        # Existing file is untouched.
        assert existing.read_text(encoding="utf-8") == "old"
        # No staging directory leaked.
        leaked = [
            p
            for p in dst.parent.iterdir()
            if p.is_dir() and p.name.startswith(".fctx_extract_")
        ]
        assert leaked == []


# -----------------------------------------------------------------------------
# Zip-slip / path-escape payloads
# -----------------------------------------------------------------------------

class TestZipSlipProtection:
    """Hostile archives must be rejected before any file is written."""

    @pytest.mark.parametrize(
        "member_name",
        [
            "../evil.txt",          # POSIX traversal
            "../../evil.txt",       # multi-level traversal
            "sub/../../evil.txt",   # traversal after a benign segment
            "/abs/evil.txt",        # absolute POSIX path
            "C:\\evil.txt",         # Windows drive (backslash)
            "C:/evil.txt",          # Windows drive (forward slash)
            "C:evil.txt",           # drive-relative Windows path
            "..\\evil.txt",         # backslash traversal
            "sub\\..\\..\\evil.txt",  # backslash multi-traversal
            "\\\\evil\\share.txt",  # UNC path
            "//evil/share.txt",     # UNC-style (forward slashes)
            "..",                   # bare traversal component
        ],
    )
    def test_zip_slip_payloads_rejected(
        self, member_name, mock_project, tmp_path
    ):
        """Every zip-slip variant is rejected and writes nothing."""
        archive = _make_zip(
            {member_name: b"pwned"}, tmp_path / "hostile.zip"
        )
        dst = mock_project / "target"

        with pytest.raises(ValueError):
            FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        # Critical invariant: nothing escaped. The hostile member must not exist
        # anywhere at/above the project root.
        evil_anywhere = list(mock_project.parent.rglob("evil.txt"))
        # Filter to results actually written by this extraction attempt.
        written = [p for p in evil_anywhere if "target" in p.parts]
        assert written == [], f"Member escaped to: {written}"
        # Destination dir may or may not have been created, but no payload.
        if dst.exists():
            assert not list(dst.rglob("evil.txt"))

    def test_zip_slip_atomic_no_partial_write(self, mock_project, tmp_path):
        """If one member is hostile, no benign members are written either."""
        archive = _make_zip(
            {"safe.txt": b"safe", "../evil.txt": b"pwned"},
            tmp_path / "mixed.zip",
        )
        dst = mock_project / "target"

        with pytest.raises(ValueError):
            FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        # Neither the safe member nor the hostile one should be present.
        assert not (dst / "safe.txt").exists()
        assert not list(mock_project.parent.rglob("evil.txt"))

    def test_safe_dot_segments_allowed(self, mock_project, tmp_path):
        """Benign ``.`` segments and nested names extract normally."""
        archive = _make_zip(
            {"./ok.txt": b"ok", "a/./b.txt": b"ab"},
            tmp_path / "dots.zip",
        )
        dst = mock_project / "target"

        result = FileOps.extract_archive(str(archive), str(dst), str(mock_project))

        assert (dst / "ok.txt").read_bytes() == b"ok"
        assert (dst / "a" / "b.txt").read_bytes() == b"ab"
        assert len(result) >= 2
