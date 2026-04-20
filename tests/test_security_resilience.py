import os
import threading
from unittest.mock import patch

import pytest

from file_cortex_core import ActionBridge, FileUtils, PathValidator

# -----------------------------------------------------------------------------
# 1. Path Safety & Normalization Matrix
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("path,root,expected_safe", [
    ("../../etc/passwd", "C:/User/Project", False),
    ("C:/Windows/System32", "C:/User/Project", False),
    ("//localhost/c$/evil", "C:/Project", False),
])
def test_security_path_validator_matrix(path, root, expected_safe):
    """Core security matrix: Traversal, Windows System Paths, and UNC blocking."""
    assert PathValidator.is_safe(path, root) == expected_safe

def test_security_path_safe_relative(tmp_path):
    """Relative paths resolve within root when root exists."""
    (tmp_path / "src").mkdir()
    result = PathValidator.is_safe("src/main.py", str(tmp_path))
    assert result is True

def test_security_path_safe_absolute_nested(tmp_path):
    """Absolute paths under root are safe."""
    (tmp_path / "src").mkdir()
    nested = tmp_path / "src" / "main.py"
    nested.write_text("test", encoding="utf-8")
    result = PathValidator.is_safe(str(nested), str(tmp_path))
    assert result is True

def test_security_path_safe_parent_traversal(tmp_path):
    """Traversal with .. should still resolve safely within root."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "file.txt").write_text("x", encoding="utf-8")
    result = PathValidator.is_safe("subdir/../subdir/file.txt", str(tmp_path))
    assert result is True

def test_security_path_normalization_unification():
    """Verify that norm_path handles mixed slashes and redundant dots."""
    p1 = "a/b/../c\\"
    p2 = "a\\c/"
    assert PathValidator.norm_path(p1) == PathValidator.norm_path(p2)

# -----------------------------------------------------------------------------
# 2. Injection & Bridge Hardening
# -----------------------------------------------------------------------------

def test_security_action_bridge_injection_block(tmp_path):
    """Verify that attempts to break out of command templates are blocked."""
    # Create the malicious-looking file to pass exists() check
    malicious_name = "test.txt ; rm -rf"
    f = tmp_path / malicious_name
    f.write_text("dummy")

    template = "type {path}"

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 1234
        mock_popen.return_value.poll.return_value = 0
        mock_popen.return_value.communicate.return_value = (b"", b"")

        list(ActionBridge.stream_tool(template, str(f), str(tmp_path)))

        args, kwargs = mock_popen.call_args
        cmd = args[0]
        # On Unix-like systems we should stay in shell=False list-mode for safety.
        # On Windows, shell=True may be used for builtins like `type`.
        if os.name == "nt":
            assert kwargs.get("shell") is True
            assert isinstance(cmd, str)
            assert str(f).replace('"', '\\"') in cmd
        else:
            assert kwargs.get("shell") is False
            assert isinstance(cmd, list)
            assert cmd[0] == "type"
            assert cmd[1] == str(f)
            # Ensure malicious shell metacharacters remain data inside one arg.
            assert ";" in cmd[1]

# -----------------------------------------------------------------------------
# 3. Resource Cleanup & Concurrency
# -----------------------------------------------------------------------------

def test_resilience_resource_leak_audit(mock_project):
    """Verify os.scandir and file handles are released correctly."""
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        # Trigger directory listing
        for _ in range(10):
            list(FileUtils.get_project_items(str(mock_project), [], True))

        # Check for ResourceWarnings (like unclosed scandir)
        leaks = [x for x in w if issubclass(x.category, ResourceWarning)]
        assert len(leaks) == 0

def test_resilience_concurrency_stress(clean_config):
    """High-load test for DataManager lock and ThreadPool usage."""
    dm = clean_config
    errors = []

    def task():
        try:
            for _ in range(50):
                dm.get_project_data("test_proj")
                dm.save()
        except Exception as e:
            errors.append(e)

    workers = [threading.Thread(target=task) for _ in range(10)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    assert len(errors) == 0

# -----------------------------------------------------------------------------
# 4. OS/Filesystem Edge Cases
# -----------------------------------------------------------------------------

def test_resilience_filesystem_errors(tmp_path):
    """Verify graceful handling of permission errors or missing components."""
    d = tmp_path / "protected"
    d.mkdir()
    f = d / "secret.txt"
    f.write_text("shhh")

    # Simulate permission issue (on OS level where possible, or via mock)
    with patch("os.scandir", side_effect=PermissionError("Access Denied")):
        items = FileUtils.get_project_items(str(d), [], True)
        assert items == [] # Should fail gracefully, not crash
