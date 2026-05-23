"""Shared runtime state for FileCortex routes."""

from __future__ import annotations

import subprocess
import threading

MAX_ACTIVE_PROCESSES = 50

ACTIVE_PROCESSES: dict[int, subprocess.Popen] = {}
PROCESS_LOCK = threading.Lock()


def register_process(pid: int, proc: subprocess.Popen) -> bool:
    """Registers a process, enforcing a maximum count.

    Returns:
        True if registered successfully, False if at capacity.
    """
    with PROCESS_LOCK:
        if len(ACTIVE_PROCESSES) >= MAX_ACTIVE_PROCESSES:
            return False
        ACTIVE_PROCESSES[pid] = proc
        return True


def unregister_process(pid: int) -> None:
    """Removes a process from the registry."""
    with PROCESS_LOCK:
        ACTIVE_PROCESSES.pop(pid, None)
