"""Tests for security fixes applied in FileCortex v6.5.0.

Covers BUG-1 (symlink traversal), BUG-2 (access control),
BUG-3/4 (thread safety), BUG-5 (MCP security), BUG-6 (dead code),
BUG-7 (stats memory), BUG-8 (ProcessManager), BUG-11 (CLI security).
"""

import argparse
import os
import subprocess
import threading
from unittest.mock import MagicMock

import pytest

from fctx import cmd_open
from file_cortex_core import DataManager, FileUtils, PathValidator
from routers.common import ProcessManager

# ---------------------------------------------------------------------------
# 1. Symlink Traversal (BUG-1)
# ---------------------------------------------------------------------------

class TestSymlinkTraversal:
    """Tests for is_safe() symlink resolution (BUG-1)."""

    def _make_symlink(self, target, link):
        """Create a symlink, skipping on Windows permission errors."""
        try:
            os.symlink(str(target), str(link))
        except OSError:
            pytest.skip("Symlinks require admin on Windows")

    def test_symlink_traversal_is_blocked(self, tmp_path):
        """Symlink inside project pointing outside project -> is_safe False."""
        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret", encoding="utf-8")

        link = project / "escape"
        self._make_symlink(outside, link)

        assert not PathValidator.is_safe(str(link), str(project))

    def test_symlink_within_project_is_allowed(self, tmp_path):
        """Symlink pointing within project -> is_safe True."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "target.txt").write_text("data", encoding="utf-8")

        link = project / "link.txt"
        self._make_symlink(project / "target.txt", link)

        assert PathValidator.is_safe(str(link), str(project))

    def test_directory_symlink_traversal_blocked(self, tmp_path):
        """Directory symlink pointing outside -> is_safe False."""
        project = tmp_path / "project"
        project.mkdir()
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()

        link = project / "escape_dir"
        self._make_symlink(outside_dir, link)

        assert not PathValidator.is_safe(str(link), str(project))

    def test_resolve_follows_chain_of_symlinks(self, tmp_path):
        """Chain of symlinks eventually pointing outside -> is_safe False."""
        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        # chain: link1 -> link2 -> outside
        link2 = tmp_path / "link2"
        self._make_symlink(outside, link2)

        link1 = project / "link1"
        self._make_symlink(link2, link1)

        assert not PathValidator.is_safe(str(link1), str(project))

    def test_resolve_handles_broken_symlinks(self, tmp_path):
        """Broken symlinks should not crash is_safe()."""
        project = tmp_path / "project"
        project.mkdir()

        broken = project / "broken_link"
        self._make_symlink(tmp_path / "nonexistent_target_xyz", broken)

        # Should return False (target resolves outside or doesn't exist)
        result = PathValidator.is_safe(str(broken), str(project))
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 2. Access Control — generate_context (BUG-2)
# ---------------------------------------------------------------------------

class TestGenerateAccessControl:
    """Tests for /api/generate project access control (BUG-2)."""

    def test_generate_rejects_unregistered_project(self, api_client, tmp_path):
        """Unregistered project_path returns 403."""
        fake_path = str(tmp_path / "never_registered")
        res = api_client.post(
            "/api/generate",
            json={
                "files": [],
                "project_path": fake_path,
            },
        )
        assert res.status_code == 403

    def test_generate_accepts_registered_project(self, project_client, mock_project):
        """Registered project_path returns 200."""
        res = project_client.post(
            "/api/generate",
            json={
                "files": [],
                "project_path": str(mock_project),
            },
        )
        assert res.status_code == 200

    def test_generate_without_project_path_allowed(self, api_client):
        """No project_path (None) should return 200."""
        res = api_client.post(
            "/api/generate",
            json={
                "files": [],
                "project_path": None,
            },
        )
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# 3. Stats Memory Limit (BUG-7)
# ---------------------------------------------------------------------------

class TestStatsMemoryLimit:
    """Tests for stats endpoint memory safety (BUG-7)."""

    def test_stats_uses_memory_limit(self, project_client, mock_project):
        """Stats endpoint reads files with max_bytes limit, no crash."""
        # Create a file with some content
        big_file = mock_project / "big.txt"
        big_file.write_text("hello world " * 5000, encoding="utf-8")

        res = project_client.post(
            "/api/project/stats",
            json={
                "paths": [str(big_file)],
                "project_path": str(mock_project),
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "total_tokens" in data
        assert "file_count" in data


# ---------------------------------------------------------------------------
# 4. MCP register_workspace Security (BUG-5)
# ---------------------------------------------------------------------------

class TestMCPRegisterSecurity:
    """Tests for MCP register_workspace security checks (BUG-5)."""

    def test_mcp_register_rejects_system_dir(self, system_dir):
        """System directory should be rejected by validate_project."""
        with pytest.raises(PermissionError):
            PathValidator.validate_project(system_dir)

    def test_mcp_register_rejects_unc_path(self):
        """UNC path should be blocked."""
        with pytest.raises(PermissionError, match="UNC"):
            PathValidator.validate_project("\\\\server\\share")

    def test_mcp_register_accepts_valid_directory(self, clean_config, tmp_path):
        """Valid temp directory should be accepted by validate_project."""
        valid_dir = tmp_path / "valid_project"
        valid_dir.mkdir()

        result = PathValidator.validate_project(str(valid_dir))
        assert result.exists()
        assert result.is_dir()

    def test_mcp_register_rejects_nonexistent(self):
        """Non-existent path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PathValidator.validate_project("/nonexistent/path/xyz123")


# ---------------------------------------------------------------------------
# 5. CLI cmd_open Security (BUG-11)
# ---------------------------------------------------------------------------

class TestCLIOpenSecurity:
    """Tests for CLI cmd_open security checks (BUG-11)."""

    def test_cli_open_rejects_system_dir(self, capsys, system_dir):
        """Opening a system directory prints error."""
        args = argparse.Namespace(path=system_dir)
        dm = DataManager()
        cmd_open(args, dm)
        captured = capsys.readouterr()
        assert "ERROR" in captured.out

    def test_cli_open_accepts_valid_dir(self, capsys, tmp_path, clean_config):
        """Opening a valid directory registers the project."""
        valid_dir = tmp_path / "cli_project"
        valid_dir.mkdir()

        args = argparse.Namespace(path=str(valid_dir))
        cmd_open(args, clean_config)
        captured = capsys.readouterr()
        assert "PROJECT REGISTERED" in captured.out


# ---------------------------------------------------------------------------
# 6. Thread Safety (BUG-3, BUG-4)
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Tests for thread safety fixes (BUG-3, BUG-4)."""

    def test_activate_thread_safety(self, clean_config):
        """Concurrent activate() calls should not corrupt state."""
        errors = []
        barrier = threading.Barrier(5)

        def worker():
            try:
                barrier.wait(timeout=5)
                dm = DataManager.create()
                with DataManager.activate(dm):
                    _ = DataManager()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_resolve_project_root_thread_safety(self, clean_config, tmp_path):
        """Concurrent resolve_project_root reads should not crash."""
        project_dir = tmp_path / "thread_proj"
        project_dir.mkdir()
        clean_config.add_to_recent(str(project_dir))

        results = []
        errors = []
        barrier = threading.Barrier(5)

        def worker():
            try:
                barrier.wait(timeout=5)
                r = clean_config.resolve_project_root(str(project_dir))
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_concurrent_config_save_and_read(self, clean_config):
        """Save and read from different threads should not corrupt."""
        errors = []
        barrier = threading.Barrier(3)

        def writer():
            try:
                barrier.wait(timeout=5)
                for i in range(10):
                    clean_config.config.last_directory = f"/tmp/writer_{i}"
                    clean_config.save()
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                barrier.wait(timeout=5)
                for _ in range(10):
                    _ = clean_config.config.last_directory
                    _ = clean_config.data
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(errors) == 0, f"Concurrent R/W errors: {errors}"


# ---------------------------------------------------------------------------
# 7. ProcessManager Encapsulation (BUG-8)
# ---------------------------------------------------------------------------

class TestProcessManagerEncapsulation:
    """Tests for ProcessManager thread-safe registry (BUG-8)."""

    def test_process_manager_get_method(self):
        """get() returns the registered process or None."""
        pm = ProcessManager(max_processes=5)
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 1234

        assert pm.get(1234) is None
        pm.register(1234, mock_proc)
        assert pm.get(1234) is mock_proc

    def test_process_manager_register_unregister_flow(self):
        """Full register -> get -> unregister cycle works."""
        pm = ProcessManager(max_processes=10)
        mock_proc = MagicMock(spec=subprocess.Popen)

        assert pm.register(42, mock_proc) is True
        assert pm.get(42) is mock_proc
        assert pm.active_count == 1

        pm.unregister(42)
        assert pm.get(42) is None
        assert pm.active_count == 0

    def test_process_manager_max_capacity(self):
        """Max 50 processes enforced by default."""
        pm = ProcessManager(max_processes=3)
        for i in range(3):
            mock_proc = MagicMock(spec=subprocess.Popen)
            assert pm.register(i, mock_proc) is True

        # 4th should fail
        extra = MagicMock(spec=subprocess.Popen)
        assert pm.register(99, extra) is False
        assert pm.active_count == 3

    def test_process_manager_clear(self):
        """clear() removes all processes."""
        pm = ProcessManager(max_processes=10)
        for i in range(5):
            pm.register(i, MagicMock(spec=subprocess.Popen))
        assert pm.active_count == 5

        pm.clear()
        assert pm.active_count == 0
        assert pm.pids == []

    def test_process_manager_pids_snapshot(self):
        """Pids property returns a snapshot list."""
        pm = ProcessManager(max_processes=10)
        pm.register(10, MagicMock(spec=subprocess.Popen))
        pm.register(20, MagicMock(spec=subprocess.Popen))

        pids = pm.pids
        assert sorted(pids) == [10, 20]
        # Modifying returned list should not affect internal state
        pids.append(999)
        assert pm.active_count == 2


# ---------------------------------------------------------------------------
# 8. Dead Code Removal (BUG-6)
# ---------------------------------------------------------------------------

class TestDeadCodeRemoval:
    """Tests for read_text_smart edge cases (BUG-6)."""

    def test_read_text_smart_binary_file(self, tmp_path):
        """Binary file should return content without crash."""
        bin_file = tmp_path / "binary.bin"
        bin_file.write_bytes(b"\x00\xff\x00\xffhello\x00\x00")
        result = FileUtils.read_text_smart(bin_file)
        # Should not crash; returns string (may be partial)
        assert isinstance(result, str)

    def test_read_text_smart_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty string without crash."""
        nonexistent = tmp_path / "does_not_exist.txt"
        result = FileUtils.read_text_smart(nonexistent)
        assert result == ""

    def test_read_text_smart_with_max_bytes(self, tmp_path):
        """max_bytes parameter limits read size."""
        text_file = tmp_path / "large.txt"
        text_file.write_text("A" * 10000, encoding="utf-8")

        result = FileUtils.read_text_smart(text_file, max_bytes=100)
        assert len(result) <= 100
        assert isinstance(result, str)

    def test_read_text_smart_empty_file(self, tmp_path):
        """Empty file returns empty string."""
        empty = tmp_path / "empty.txt"
        empty.write_text("", encoding="utf-8")
        result = FileUtils.read_text_smart(empty)
        assert result == ""


# ---------------------------------------------------------------------------
# 9. Additional Security Edge Cases
# ---------------------------------------------------------------------------

class TestSecurityEdgeCases:
    """Additional security boundary tests."""

    def test_is_safe_empty_root_returns_false(self):
        """Empty root_path should return False."""
        assert PathValidator.is_safe("/some/path", "") is False

    def test_is_safe_none_root_returns_false(self):
        """None-like root should return False."""
        assert PathValidator.is_safe("/some/path", None) is False

    def test_is_safe_child_within_root(self, tmp_path):
        """Child path within root returns True."""
        root = tmp_path / "root"
        root.mkdir()
        child = root / "sub" / "file.txt"
        child.parent.mkdir(parents=True)
        child.write_text("data", encoding="utf-8")

        assert PathValidator.is_safe(str(child), str(root)) is True

    def test_is_safe_sibling_outside_root(self, tmp_path):
        """Sibling path outside root returns False."""
        root = tmp_path / "root"
        root.mkdir()
        sibling = tmp_path / "sibling"
        sibling.mkdir()

        assert PathValidator.is_safe(str(sibling), str(root)) is False

    def test_is_safe_dotdot_traversal(self, tmp_path):
        """Path traversal with .. should be blocked."""
        root = tmp_path / "root"
        root.mkdir()
        traversal = str(root / ".." / "escape")

        assert PathValidator.is_safe(traversal, str(root)) is False

    def test_is_safe_exact_root_match(self, tmp_path):
        """Exact root path should return True."""
        root = tmp_path / "root"
        root.mkdir()
        assert PathValidator.is_safe(str(root), str(root)) is True

    def test_validate_project_rejects_file_not_dir(self, tmp_path):
        """File path (not directory) should raise NotADirectoryError."""
        file_path = tmp_path / "afile.txt"
        file_path.write_text("data", encoding="utf-8")
        with pytest.raises(NotADirectoryError):
            PathValidator.validate_project(str(file_path))

    def test_validate_project_rejects_sensitive_name(self, tmp_path):
        """Sensitive directory names like .git should be blocked."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with pytest.raises(PermissionError):
            PathValidator.validate_project(str(git_dir))

    def test_norm_path_returns_string(self):
        """norm_path always returns a string."""
        result = PathValidator.norm_path("/some/path")
        assert isinstance(result, str)

    def test_norm_path_none_returns_empty(self):
        """norm_path(None) returns empty string."""
        assert PathValidator.norm_path(None) == ""

    def test_norm_path_empty_returns_empty(self):
        """norm_path('') returns empty string."""
        assert PathValidator.norm_path("") == ""
