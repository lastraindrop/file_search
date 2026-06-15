"""Shared runtime state for FileCortex routes."""

from __future__ import annotations

import subprocess
import threading

from file_cortex_core.config import logger

MAX_ACTIVE_PROCESSES = 50


class ProcessManager:
    """Thread-safe registry for tracking active subprocesses.

    Provides a bounded registry that enforces a maximum number of
    concurrent active processes.
    """

    def __init__(self, max_processes: int = MAX_ACTIVE_PROCESSES) -> None:
        """Initializes the ProcessManager.

        Args:
            max_processes: Maximum number of concurrent processes.
        """
        self._max = max_processes
        self._lock = threading.Lock()
        self._processes: dict[int, subprocess.Popen] = {}

    @property
    def active_count(self) -> int:
        """Returns the number of currently active processes."""
        with self._lock:
            return len(self._processes)

    def register(self, pid: int, proc: subprocess.Popen) -> bool:
        """Registers a process, enforcing the maximum count.

        Args:
            pid: Process ID.
            proc: Popen object.

        Returns:
            True if registered successfully, False if at capacity or PID in use.
        """
        with self._lock:
            if len(self._processes) >= self._max:
                return False
            existing = self._processes.get(pid)
            # BUG-W5 fix: refuse to overwrite a still-live process entry.
            if existing is not None and existing.poll() is None:
                logger.warning(
                    f"PID {pid} already registered with a live process; "
                    f"refusing overwrite."
                )
                return False
            self._processes[pid] = proc
            return True

    def unregister(self, pid: int) -> None:
        """Removes a process from the registry.

        Args:
            pid: Process ID to remove.
        """
        with self._lock:
            self._processes.pop(pid, None)

    def get(self, pid: int) -> subprocess.Popen | None:
        """Retrieves a registered process by PID.

        Args:
            pid: Process ID.

        Returns:
            The Popen object, or None if not found.
        """
        with self._lock:
            return self._processes.get(pid)

    def clear(self) -> None:
        """Removes all processes from the registry."""
        with self._lock:
            self._processes.clear()

    @property
    def pids(self) -> list[int]:
        """Returns a snapshot of all registered PIDs."""
        with self._lock:
            return list(self._processes.keys())


# Module-level singleton for backward compatibility
process_manager = ProcessManager()

# Legacy aliases for backward compatibility with existing code
ACTIVE_PROCESSES = process_manager._processes
PROCESS_LOCK = process_manager._lock


def register_process(pid: int, proc: subprocess.Popen) -> bool:
    """Registers a process via the global ProcessManager."""
    return process_manager.register(pid, proc)


def unregister_process(pid: int) -> None:
    """Unregisters a process via the global ProcessManager."""
    process_manager.unregister(pid)
