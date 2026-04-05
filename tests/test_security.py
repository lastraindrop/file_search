import pytest
import os
import pathlib
from file_cortex_core import PathValidator

def test_path_validator_is_safe_comprehensive(mock_project, system_dir):
    """Verify robust path traversal defense."""
    root = str(mock_project.resolve())
    
    # --- Safe Paths ---
    assert PathValidator.is_safe(str(mock_project / "src"), root) is True
    assert PathValidator.is_safe(str(mock_project / "src" / "main.py"), root) is True
    
    # --- Unsafe: Parent traversal ---
    assert PathValidator.is_safe(str(mock_project / ".." / "outside"), root) is False
    assert PathValidator.is_safe(str(mock_project / "src" / ".." / ".." / "etc" / "passwd"), root) is False
    assert PathValidator.is_safe(os.path.join(root, ".."), root) is False

    # --- Windows Specific Extended Paths (Bypass attempts) ---
    if os.name == 'nt':
        assert PathValidator.is_safe(r"\\?\C:\Windows\System32", root) is False
        assert PathValidator.is_safe(r"//?/C:/Windows", root) is False
        assert PathValidator.is_safe(r"C:..\..\Windows", root) is False

    # --- Neutral Traversal (Should be safe) ---
    assert PathValidator.is_safe(os.path.join(root, ".", "src"), root) is True
    assert PathValidator.is_safe(os.path.join(root, "src", "..", "src", "main.py"), root) is True

    # --- Unsafe: Fake Prefix ---
    # root: /fake/proj
    # fake_root: /fake/proj_fake
    fake_root = str(mock_project.parent / (mock_project.name + "_fake"))
    assert PathValidator.is_safe(fake_root, root) is False

    # --- Unsafe: Absolute system path (No-Hardcode) ---
    assert PathValidator.is_safe(system_dir, root) is False

def test_path_validator_blocked_prefixes(system_dir):
    """Verify that system directories (prefixes) are blocked."""
    from file_cortex_core import PathValidator
    with pytest.raises(PermissionError) as exc:
        PathValidator.validate_project(system_dir)
    assert "Access to system directory" in str(exc.value)

def test_path_validator_allows_user_dirs_with_system_keywords(tmp_path):
    """Verify that user dirs named 'windows-app' or 'etc-notes' are NOT blocked."""
    # Create a dir whose name contains a keyword but is NOT a system dir
    user_dir = tmp_path / "windows_test"
    user_dir.mkdir()
    # Should NOT raise PermissionError
    p = PathValidator.validate_project(str(user_dir))
    assert p.exists()

def test_path_validator_root_drive_blocked():
    """Verify that root drives ('C:/' or '/') are blocked."""
    from file_cortex_core import PathValidator
    import sys
    root = "C:/" if sys.platform == 'win32' else "/"
    with pytest.raises(PermissionError) as exc:
        PathValidator.validate_project(root)
    assert "root drive" in str(exc.value)

def test_path_validator_non_existent():
    """Raising FileNotFoundError for garbage paths."""
    with pytest.raises(FileNotFoundError):
        PathValidator.validate_project("/path/to/nowhere_xyz_123")
