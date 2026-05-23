"""Cross-platform process termination utilities for FileCortex."""

import contextlib
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def terminate_process(pid: int) -> None:
    """Forcefully terminate a process and its children.

    On Windows, uses taskkill /F /T. On POSIX, sends SIGTERM to
    the process group, falling back to process.kill().

    Args:
        pid: The process ID to terminate.
    """
    if not pid:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
            )
        else:
            import signal

            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception as exc:
        logger.warning("Failed to terminate process %d: %s", pid, exc)
