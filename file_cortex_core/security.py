import pathlib
import os
import sys

class PathValidator:
    @staticmethod
    def is_safe(target_path, root_path):
        """Strict check to prevent path traversal outside project root."""
        try:
            # resolve() handles '..' and case-normalization
            target = pathlib.Path(target_path).resolve()
            root = pathlib.Path(root_path).resolve()
            
            # Explicitly check for traversal before is_relative_to for older Python versions
            if ".." in str(target_path) or ".." in str(pathlib.Path(target_path).as_posix()):
                 # This is a red flag, though resolve() should handle it.
                 pass

            if hasattr(target, 'is_relative_to'):
                 return target.is_relative_to(root)
            # Fallback for Python < 3.9
            return root == target or root in target.parents
        except Exception:
            return False

    @staticmethod
    def norm_path(p: str | pathlib.Path | None) -> str:
        """Canonicalize path: absolute, lowercase, posix-style, and trail-slash standardized."""
        if not p: return ""
        try:
            # Use os.path.abspath for industrial-strength determinism on Windows
            p_str = os.path.abspath(str(p)).replace('\\', '/').lower()
            
            # Protection for roots:
            # Unix root: '/'
            if p_str == '/': return '/'
            # Windows drive root: 'c:/'
            if len(p_str) == 3 and p_str[1:3] == ':/': return p_str
            
            # Standard paths: remove trailing slash
            return p_str.rstrip('/')
        except Exception:
            s = str(p).lower().replace('\\', '/')
            if s == '/': return '/'
            if len(s) == 3 and s[1:3] == ':/': return s
            return s.rstrip('/')

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
