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

    # --- Unsafe: Fake Prefix ---
    # root: /fake/proj
    # fake_root: /fake/proj_fake
    fake_root = str(mock_project.parent / (mock_project.name + "_fake"))
    assert PathValidator.is_safe(fake_root, root) is False

    # --- Unsafe: Absolute system path (No-Hardcode) ---
    assert PathValidator.is_safe(system_dir, root) is False

def test_path_validator_blocked_keywords():
    """Verify that sensitive system directories are blocked upon project registration."""
    # Mocking existence and resolution to avoid environment-specific failures
    from unittest.mock import patch, MagicMock
    import pathlib

    # Test several blocked patterns
    blocked = ["C:/Windows", "/etc", "/usr/bin", "C:/Program Files/System32"]
    for b in blocked:
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_dir', return_value=True):
            with pytest.raises(PermissionError):
                PathValidator.validate_project(b)

def test_path_validator_root_drive():
    """Prevent registering the root drive."""
    root_drive = "C:/" if os.name == "nt" else "/"
    with pytest.raises(PermissionError):
        PathValidator.validate_project(root_drive)

def test_path_validator_non_existent():
    """Raising FileNotFoundError for garbage paths."""
    with pytest.raises(FileNotFoundError):
        PathValidator.validate_project("/path/to/nowhere_xyz_123")
