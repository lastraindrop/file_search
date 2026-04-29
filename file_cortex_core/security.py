#!/usr/bin/env python3
"""Security module for FileCortex.

Provides path validation and security checks to prevent unauthorized
file system access.
"""

import ntpath
import os
import pathlib
import sys
from typing import Final

# Constants for path validation
UNC_PREFIXES: Final = ("\\\\", "//")


class PathValidator:
    """Validates and standardizes file system paths for security.

    Provides mechanisms to prevent directory traversal attacks and ensure
    deterministic path keys across different operating systems.
    """

    @staticmethod
    def is_safe(target_path: str | pathlib.Path, root_path: str | pathlib.Path) -> bool:
        """Checks if a target path is securely contained within a root path.

        Args:
            target_path: The file or directory path to validate.
            root_path: The directory acting as the security boundary.

        Returns:
            True if the target_path is within root_path and not using unsafe
            constructs like UNC paths on Windows (unless explicitly allowed).
            Returns False if root_path is empty or if an error occurs.
        """
        if not root_path:
            return False
        try:
            target_raw = str(target_path)
            root_raw = str(root_path)

            # Detect Windows-style paths (drive letters or UNC)
            is_windows_target = (
                bool(ntpath.splitdrive(target_raw)[0])
                or target_raw.startswith(UNC_PREFIXES)
            )
            is_windows_root = (
                bool(ntpath.splitdrive(root_raw)[0])
                or root_raw.startswith(UNC_PREFIXES)
            )

            if is_windows_target or is_windows_root:
                # Disallow UNC paths as they can lead to credential leaking
                if target_raw.startswith(UNC_PREFIXES):
                    return False

                # Normalize using ntpath for deterministic Windows logic
                root_norm = ntpath.normpath(root_raw).replace("/", "\\").lower()

                # Handle relative targets by joining with root
                target_norm_raw = target_raw
                if not ntpath.isabs(target_norm_raw):
                    target_norm_raw = ntpath.join(root_raw, target_norm_raw)

                target_norm = ntpath.normpath(target_norm_raw).replace("/", "\\").lower()

                # Boundary check
                root_prefix = root_norm.rstrip("\\") + "\\"
                return target_norm == root_norm or target_norm.startswith(root_prefix)

            # POSIX-style logic using abspath for virtual paths (non-existent)
            root_norm = os.path.abspath(root_raw)

            target_norm_raw = target_raw
            if not os.path.isabs(target_norm_raw):
                target_norm_raw = os.path.join(root_norm, target_norm_raw)

            target_norm = os.path.abspath(target_norm_raw)

            root_prefix = root_norm.rstrip(os.sep) + os.sep
            return target_norm == root_norm or target_norm.startswith(root_prefix)
        except (ValueError, OSError):
            return False

    @staticmethod
    def norm_path(p: str | pathlib.Path | None) -> str:
        """Standardizes a path into a canonical POSIX-style string.

        Converts backslashes to forward slashes, standardizes drive casing on
        Windows, and removes trailing slashes (except for roots).

        Args:
            p: The path string or object to normalize.

        Returns:
            A normalized POSIX-style path string. Returns empty string if input is empty.
        """
        if p is None:
            return ""

        s = str(p).strip()
        if not s:
            return ""

        try:
            # Physical normalization
            path_str = os.path.abspath(s).replace("\\", "/")
        except (ValueError, OSError):
            # Logical fallback if abspath fails
            path_str = s.replace("\\", "/")

        if sys.platform == "win32":
            path_str = path_str.lower()
            # Standardize Windows long path prefixes
            if path_str.startswith("//?/"):
                path_str = path_str[4:]

            # Handle drive roots: "c:/" remains "c:/"
            if len(path_str) == 3 and path_str[1:3] == ":/":
                return path_str
        elif path_str == "/":
            # POSIX root: "/" remains "/"
            return "/"

        # Standardize by removing trailing slashes for all non-root paths
        return path_str.rstrip("/")

    @staticmethod
    def validate_project(path_str: str) -> pathlib.Path:
        """Validates and returns a secure project path.

        Ensures the path exists, is a directory, and is not a sensitive
        system or blacklisted directory.

        Args:
            path_str: The directory path to validate.

        Returns:
            A resolved pathlib.Path object.

        Raises:
            PermissionError: If the path is blocked for security reasons (UNC, System, etc.).
            FileNotFoundError: If the path does not exist on disk.
            NotADirectoryError: If the path exists but is not a directory.
        """
        normalized_str = (
            str(path_str).replace("/", "\\") if sys.platform == "win32" else str(path_str)
        )

        if sys.platform == "win32" and normalized_str.startswith("\\\\"):
            raise PermissionError(
                "UNC/Network paths are blocked to prevent potential SMB credential leaks."
            )

        p = pathlib.Path(path_str).resolve()

        if not p.exists():
            raise FileNotFoundError(f"Project path does not exist: {path_str}")
        if not p.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path_str}")

        # Block sensitive development directories from being registered as roots
        sensitive_names = {".git", ".env", "__pycache__", "node_modules", ".idea", ".vscode"}
        if p.name.lower() in sensitive_names:
            raise PermissionError(
                f"Cannot register sensitive directory as project root: {p.name}"
            )

        if len(p.parts) <= 1:
            raise PermissionError("Cannot register system root drive as a project.")

        # Platform-specific system directory protection
        blocked_prefixes = []
        if sys.platform == "win32":
            blocked_prefixes = [
                pathlib.Path(os.environ.get("SYSTEMROOT", "C:/Windows")).resolve(),
                pathlib.Path(os.environ.get("PROGRAMFILES", "C:/Program Files")).resolve(),
                pathlib.Path(
                    os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")
                ).resolve(),
            ]
        else:
            blocked_prefixes = [
                pathlib.Path(d).resolve()
                for d in [
                    "/etc",
                    "/usr",
                    "/bin",
                    "/sbin",
                    "/boot",
                    "/var",
                    "/proc",
                    "/sys",
                    "/dev",
                ]
            ]

        for blocked in blocked_prefixes:
            if p == blocked or blocked in p.parents:
                raise PermissionError(f"Access to system directory '{blocked}' is blocked.")

        return p
