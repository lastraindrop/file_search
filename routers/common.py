"""Shared runtime state for FileCortex routes."""

from __future__ import annotations

import subprocess
import threading


# Global process registry for tool execution
ACTIVE_PROCESSES: dict[int, subprocess.Popen] = {}
PROCESS_LOCK = threading.Lock()
