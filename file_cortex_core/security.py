#!/usr/bin/env python3
"""Security module for FileCortex.

Provides path validation and security checks to prevent unauthorized
file system access.
"""

import ntpath
import os
import pathlib
import sys

UNC_PREFIXES = ('\\\\', '//')


class PathValidator:
    """Validates paths to prevent path traversal attacks."""

    @staticmethod
    def is_safe(target_path: str | pathlib.Path, root_path: str | pathlib.Path) -> bool:
        """Checks if a target path is within the root path.

        Args:
            target_path: The path to validate.
            root_path: The root directory to check against.

        Returns:
            True if the path is safe, False otherwise.
        """
        if not root_path:
            return False
        try:
            target_raw = str(target_path)
            root_raw = str(root_path)

            # Detect if we are dealing with Windows-style paths (drive letters or UNC)
            is_windows_target = (
                bool(ntpath.splitdrive(target_raw)[0])
                or target_raw.startswith(UNC_PREFIXES)
            )
            is_windows_root = (
                bool(ntpath.splitdrive(root_raw)[0])
                or root_raw.startswith(UNC_PREFIXES)
            )

            if is_windows_target or is_windows_root:
                if target_raw.startswith(UNC_PREFIXES):
                    return False

                # Normalize using ntpath for Windows logic
                root_norm = ntpath.normpath(root_raw).replace("/", "\\").lower()
                
                # If target is relative, join it to root first
                target_norm_raw = target_raw
                if not ntpath.isabs(target_norm_raw):
                    target_norm_raw = ntpath.join(root_raw, target_norm_raw)
                
                target_norm = ntpath.normpath(target_norm_raw).replace("/", "\\").lower()
                
                # Prefix check: target must be root or inside root
                root_prefix = root_norm.rstrip("\\") + "\\"
                return (target_norm == root_norm or target_norm.startswith(root_prefix))

            # POSIX-style logic
            # Use abspath for normalization which doesn't require path existence
            root_norm = os.path.abspath(root_raw)
            
            target_norm_raw = target_raw
            if not os.path.isabs(target_norm_raw):
                target_norm_raw = os.path.join(root_norm, target_norm_raw)
            
            target_norm = os.path.abspath(target_norm_raw)
            
            root_prefix = root_norm.rstrip(os.sep) + os.sep
            return (target_norm == root_norm or target_norm.startswith(root_prefix))
        except Exception:
            return False

    @staticmethod
    def norm_path(p: str | pathlib.Path | None) -> str:
        """Canonicalize path: absolute, platform-aware casing, posix-style.

        Standardizes separators and removes trailing slashes except for roots.
        """
        if p is None:
            return ""

        s = str(p).strip()
        if not s:
            return ""

        try:
            # Attempt physical normalization
            path_str = os.path.abspath(s).replace("\\", "/")
        except Exception:
            # Fallback to logical string cleanup if abspath fails
            path_str = s.replace("\\", "/")

        if sys.platform == "win32":
            path_str = path_str.lower()
            # Standardize long path prefixes if they exist
            if path_str.startswith("//?/"):
                path_str = path_str[4:]

            # Drive roots: "c:/" remains "c:/"
            if len(path_str) == 3 and path_str[1:3] == ":/":
                return path_str
        else:
            # POSIX root: "/" remains "/"
            if path_str == "/":
                return "/"

        # Remove trailing slashes for all non-root paths
        return path_str.rstrip("/")

    @staticmethod
    def validate_project(path_str: str) -> pathlib.Path:
        """Validates and returns a project path.

        Args:
            path_str: The path to validate.

        Returns:
            The validated path as a pathlib.Path.

        Raises:
            PermissionError: If the path is blocked for security reasons.
            FileNotFoundError: If the path does not exist.
            NotADirectoryError: If the path is not a directory.
        """
        normalized_str = (
            str(path_str).replace("/", "\\")
            if sys.platform == "win32"
            else str(path_str)
        )

        if sys.platform == "win32" and normalized_str.startswith("\\\\"):
            raise PermissionError(
                "UNC/Network paths are blocked for security "
                "(Potential SMB credential leak)."
            )

        p = pathlib.Path(path_str).resolve()

        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {path_str}")
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {path_str}")

        sensitive_names = {
            ".git",
            ".env",
            "__pycache__",
            "node_modules",
            ".idea",
            ".vscode",
        }
        if p.name.lower() in sensitive_names:
            raise PermissionError(
                f"Cannot register sensitive directory as project root: {p.name}"
            )

        if len(p.parts) <= 1:
            raise PermissionError("Cannot register root drive as a project.")

        blocked_prefixes = []
        if sys.platform == "win32":
            blocked_prefixes = [
                pathlib.Path(os.environ.get("SYSTEMROOT", "C:/Windows")).resolve(),
                pathlib.Path(
                    os.environ.get("PROGRAMFILES", "C:/Program Files")
                ).resolve(),
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
                raise PermissionError(
                    f"Access to system directory '{blocked}' is blocked."
                )
        return p
