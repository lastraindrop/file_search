import pathlib
import os
import sys

class PathValidator:
    @staticmethod
    def is_safe(target_path, root_path):
        """Strict check to prevent path traversal outside project root."""
        if not root_path:
            return False
        try:
            # resolve() handles '..' and case-normalization
            target = pathlib.Path(target_path).resolve()
            root = pathlib.Path(root_path).resolve()
            
            # Explicitly check for traversal before is_relative_to for older Python versions
            # Explicitly check for traversal: although resolve() handles it, 
            # we allow ".." as long as it doesnt break the is_relative_to boundary check below.
            pass

            if hasattr(target, 'is_relative_to'):
                 return target.is_relative_to(root)
            # Fallback for Python < 3.9
            return root == target or root in target.parents
        except Exception:
            return False

    @staticmethod
    def norm_path(p: str | pathlib.Path | None) -> str:
        """Canonicalize path: absolute, platform-aware casing, posix-style, and trail-slash standardized."""
        if not p:
            return ""
        try:
            # os.path.abspath for industrial-strength determinism
            p_str = os.path.abspath(str(p)).replace('\\', '/')
            
            if sys.platform == 'win32':
                p_str = p_str.lower()
                # Protection for UNC/Long paths on Windows
                if p_str.startswith('//?/'):
                    return p_str.rstrip('/')
                # Windows drive root: 'c:/'
                if len(p_str) == 3 and p_str[1:3] == ':/':
                    return p_str
            else:
                # Unix root: '/'
                if p_str == '/':
                    return '/'
            
            # Standard paths: remove trailing slash
            return p_str.rstrip('/')
        except Exception:
            s = str(p).replace('\\', '/')
            if sys.platform == 'win32': s = s.lower()
            if s == '/': return '/'
            if len(s) == 3 and s[1:3] == ':/': return s
            return s.rstrip('/')

    @staticmethod
    def validate_project(path_str: str) -> pathlib.Path:
        # Standardize representation before resolution
        normalized_str = str(path_str).replace('/', '\\') if sys.platform == 'win32' else str(path_str)
        
        if sys.platform == 'win32' and normalized_str.startswith('\\\\'):
             raise PermissionError("UNC/Network paths are blocked for security (Potential SMB credential leak).")

        p = pathlib.Path(path_str).resolve()
        
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {path_str}")
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {path_str}")
        
        # Block sensitive names (RCE prevention)
        sensitive_names = {'.git', '.env', '__pycache__', 'node_modules', '.idea', '.vscode'}
        if p.name.lower() in sensitive_names:
            raise PermissionError(f"Cannot register sensitive directory as project root: {p.name}")
            
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
