# ruff: noqa: I001, D403
"""Targeted tests for thin-coverage modules.

Supplements the test suite with coverage for:
- process_utils.terminate_process (platform-specific behavior)
- routers/common ProcessManager (registration, capacity, lifecycle)
- ActionBridge streaming mode edge cases
- Version and config constant validation
"""

import os
import threading
from unittest.mock import MagicMock, patch

import pytest

from file_cortex_core import process_utils


class TestTerminateProcess:
    """Tests for cross-platform process termination."""

    def test_terminate_none_pid_does_nothing(self):
        """Terminate with None/0 PID is silently ignored."""
        process_utils.terminate_process(0)
        process_utils.terminate_process(None)

    def test_terminate_runs_taskkill_on_windows(self):
        """On Windows terminate_process calls taskkill."""
        if os.name != "nt":
            pytest.skip("Windows-only test")
        with patch("subprocess.run") as mock_run:
            process_utils.terminate_process(12345)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "taskkill" in args
            assert "12345" in map(str, args)

    def test_terminate_catches_generic_error(self):
        """Generic exception during terminate is logged."""
        with patch("subprocess.run", side_effect=OSError("mock error")):
            process_utils.terminate_process(99999)

    def test_terminate_handles_invalid_pid(self):
        """Non-existent PID does not raise."""
        process_utils.terminate_process(99999999)


class TestCommonModule:
    """Tests for routers.common module ProcessManager and functions."""

    def test_register_process_returns_true(self):
        """register_process adds process and returns True."""
        from routers.common import register_process, process_manager

        mock_proc = MagicMock()
        mock_proc.pid = 42001
        assert register_process(42001, mock_proc) is True
        assert process_manager.get(42001) is not None
        process_manager.unregister(42001)

    def test_register_process_fails_at_capacity(self):
        """register_process returns False when at capacity (=50)."""
        from routers.common import register_process, process_manager

        process_manager.clear()
        try:
            for i in range(50):
                mock_proc = MagicMock()
                mock_proc.pid = 50000 + i
                assert register_process(50000 + i, mock_proc) is True
            overflow = MagicMock()
            overflow.pid = 50100
            assert register_process(50100, overflow) is False
        finally:
            process_manager.clear()

    def test_unregister_removes_process(self):
        """unregister removes previously registered process."""
        from routers.common import register_process, unregister_process, process_manager

        process_manager.clear()
        try:
            mock_proc = MagicMock()
            mock_proc.pid = 44001
            register_process(44001, mock_proc)
            assert process_manager.get(44001) is not None
            unregister_process(44001)
            assert process_manager.get(44001) is None
        finally:
            process_manager.clear()

    def test_process_manager_max_default(self):
        """Default ProcessManager max_processes is 50."""
        from routers.common import ProcessManager

        pm = ProcessManager()
        assert pm._max == 50

    def test_process_manager_custom_capacity(self):
        """ProcessManager accepts custom max_processes."""
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=3)
        assert pm._max == 3

    def test_active_count_reflects_registered(self):
        """active_count tracks number of registered processes."""
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=10)
        assert pm.active_count == 0
        pm.register(1, MagicMock())
        pm.register(2, MagicMock())
        assert pm.active_count == 2
        pm.unregister(1)
        assert pm.active_count == 1
        pm.clear()

    def test_clear_removes_all(self):
        """clear() removes all processes."""
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=10)
        for i in range(5):
            pm.register(100 + i, MagicMock())
        assert pm.active_count == 5
        pm.clear()
        assert pm.active_count == 0
        assert pm.pids == []

    def test_pids_snapshot_is_copy(self):
        """Pids returns a copy, not a reference to internal state."""
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=10)
        pm.register(10, MagicMock())
        pids_copy = pm.pids
        pm.register(20, MagicMock())
        assert pids_copy != pm.pids

    def test_legacy_aliases_accessible(self):
        """Legacy ACTIVE_PROCESSES and PROCESS_LOCK are accessible."""
        from routers.common import ACTIVE_PROCESSES, PROCESS_LOCK

        assert isinstance(ACTIVE_PROCESSES, dict)
        assert isinstance(PROCESS_LOCK, type(threading.Lock()))


class TestSearchPoolShutdown:
    """Tests for search pool graceful shutdown behavior."""

    def test_search_pool_not_shut_down_yet(self):
        """Shared search pool is initialized and accepts submissions.

        Uses the public behavioral contract (successful submit + result)
        rather than the private ``_shutdown`` attribute, which is a CPython
        implementation detail and not part of the ``ThreadPoolExecutor`` API.
        """
        from file_cortex_core.search import SHARED_SEARCH_POOL

        fut = SHARED_SEARCH_POOL.submit(lambda: True)
        assert fut.result(timeout=5) is True


class TestConfigConstants:
    """Tests for config module constants."""

    def test_max_save_retries_positive(self):
        """MAX_SAVE_RETRIES is a positive integer."""
        from file_cortex_core.config import MAX_SAVE_RETRIES

        assert isinstance(MAX_SAVE_RETRIES, int)
        assert MAX_SAVE_RETRIES > 0

    def test_app_name_constant(self):
        """APP_NAME is defined."""
        from file_cortex_core.config import APP_NAME

        assert isinstance(APP_NAME, str)
        assert len(APP_NAME) > 0


class TestVersionExport:
    """Tests for version export consistency."""

    def test_version_is_accessible(self):
        """__version__ is a non-empty string."""
        from file_cortex_core import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0
        parts = __version__.split(".")
        assert len(parts) >= 2

    def test_version_not_in_all(self):
        """__version__ is internal (not in __all__)."""
        from file_cortex_core import __all__ as all_exports

        assert "__version__" not in all_exports


class TestActionBridgeStreaming:
    """Tests for ActionBridge streaming mode edge cases."""

    def test_stream_tool_nonexistent_path(self, tmp_path):
        """Stream on non-existent file yields error."""
        from file_cortex_core import ActionBridge

        results = list(ActionBridge.stream_tool(
            "echo {path}", str(tmp_path / "nonexistent.txt"), str(tmp_path),
        ))
        assert len(results) >= 1
        assert "error" in results[0]

    def test_create_process_basic(self, mock_project, mock_popen):
        """create_process uses the mocked Popen."""
        from file_cortex_core import ActionBridge

        proc = ActionBridge.create_process(
            "echo hello", str(mock_project / "src" / "main.py"), str(mock_project),
        )
        assert proc is not None
