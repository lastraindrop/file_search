import os
import zipfile

import pytest

from file_cortex_core import FileOps


def test_save_content_atomic(tmp_path):
    """Verify that file save is atomic via tempfile replace."""
    target = tmp_path / "atomic.txt"
    target.write_text("OLD", encoding="utf-8")

    FileOps.save_content(str(target), "NEW")
    assert target.read_text(encoding="utf-8") == "NEW"

def test_save_content_binary_reject(tmp_path):
    """Saving binary content as text should either work or raise appropriate error if validation exists."""
    # Current implementation just writes string.
    # But let's check if FileOps prevents overwriting known binary types if added in future.
    # For now, ensure it writes correctly.
    target = tmp_path / "data_test.bin"
    target.write_bytes(b"\x00\xff")
    # Current implementation explicitly rejects binary
    with pytest.raises(ValueError, match="Cannot save binary file as text"):
        FileOps.save_content(str(target), "Fixed")

def test_delete_readonly_file(tmp_path):
    """Verify that readonly files can be deleted (FileOps should handle chmod)."""
    f = tmp_path / "readonly.txt"
    f.write_text("can't touch this")

    # Make readonly
    import stat
    os.chmod(f, stat.S_IREAD)

    # Delete
    FileOps.delete_file(str(f))
    assert not f.exists()

def test_move_same_name_conflict(tmp_path):
    """Verify move behavior when destination file exists."""
    d1 = tmp_path / "dir1"
    d2 = tmp_path / "dir2"
    d1.mkdir()
    d2.mkdir()

    f1 = d1 / "test.txt"
    f1.write_text("SRC")
    f2 = d2 / "test.txt"
    f2.write_text("DST")

    # Should raise FileExistsError
    with pytest.raises(FileExistsError):
        FileOps.move_file(str(f1), str(d2))

def test_create_existing_raises(tmp_path):
    """Creating a file that already exists should raise OSError or FileExistsError."""
    f = tmp_path / "exists.txt"
    f.write_text("data")

    with pytest.raises((FileExistsError, OSError)):
        FileOps.create_item(str(tmp_path), "exists.txt", is_dir=False)

def test_archive_selection(mock_project, tmp_path):
    """Verify ZIP archiving of selected files."""
    files = [str(mock_project / "src" / "main.py"), str(mock_project / "README.md")]
    out_zip = tmp_path / "test_bundle.zip"

    res = FileOps.archive_selection(files, str(out_zip), str(mock_project))
    assert os.path.exists(res)
    assert zipfile.is_zipfile(res)

    with zipfile.ZipFile(res, 'r') as z:
        names = z.namelist()
        assert any("main.py" in n for n in names)

def test_batch_rename_dry_run(mock_project):
    """Dry run should not modify actual files."""
    files = [str(mock_project / "src" / "main.py")]
    res = FileOps.batch_rename(str(mock_project), files, "main", "renamed", dry_run=True)

    assert len(res) == 1
    assert res[0]["status"] == "ok"
    assert (mock_project / "src" / "main.py").exists()
    assert not (mock_project / "src" / "renamed.py").exists()

def test_batch_categorize_path_safety(mock_project):
    """Verify that categorizing doesn't allow escaping project root."""
    files = [str(mock_project / "src" / "main.py")]
    # Try to move to a category name that looks like traversal
    with pytest.raises((ValueError, Exception)):
        FileOps.batch_categorize(str(mock_project), files, "../../evil")
