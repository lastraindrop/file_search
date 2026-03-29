import pathlib
import os
import sys

class PathValidator:
    @staticmethod
    def is_safe(target_path, root_path):
        """Strict check to prevent path traversal outside project root."""
        try:
            target = pathlib.Path(target_path).resolve()
            root = pathlib.Path(root_path).resolve()
            if hasattr(target, 'is_relative_to'):
                 return target.is_relative_to(root)
            return root == target or root in target.parents
        except Exception:
            return False

    @staticmethod
    def norm_path(p: str | pathlib.Path | None) -> str:
        """Canonicalize path for comparison: resolve, lowercase, and use forward slashes."""
        if p is None: return ""
        try:
            # resolve() handles '..' and case-normalization on most Windows versions
            resolved = pathlib.Path(p).resolve()
            # On some Windows environments, resolve() still returns varying casing for the drive letter
            # We enforce lowercase and forward slashes for a unique dictionary key.
            return str(resolved).lower().replace('\\', '/')
        except Exception:
            # Fallback if resolve fails (e.g. path too long or invalid)
            return str(p).lower().replace('\\', '/')

    @staticmethod
    def validate_project(path_str: str) -> pathlib.Path:
        p = pathlib.Path(path_str).resolve()
        if not p.exists(): raise FileNotFoundError(f"Path does not exist: {path_str}")
        if not p.is_dir(): raise NotADirectoryError(f"Not a directory: {path_str}")
        
        # Block root drives first
        if len(p.parts) <= 1:
            raise PermissionError("Cannot register root drive as a project.")
        
        # Only block if the directory IS or is inside a system directory (prefix-match)
        blocked_prefixes = []
        if sys.platform == 'win32':
            blocked_prefixes = [
                pathlib.Path(os.environ.get("SYSTEMROOT", "C:/Windows")).resolve(),
                pathlib.Path(os.environ.get("PROGRAMFILES", "C:/Program Files")).resolve(),
                pathlib.Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")).resolve(),
            ]
        else:
            blocked_prefixes = [pathlib.Path(d).resolve() for d in 
                               ["/etc", "/usr", "/bin", "/sbin", "/boot", "/var", "/proc", "/sys", "/dev"]]
        
        for blocked in blocked_prefixes:
            # Block if p IS a system dir or p is INSIDE a system dir
            if p == blocked or blocked in p.parents:
                raise PermissionError(f"Access to system directory '{blocked}' is blocked for security.")
        return p
