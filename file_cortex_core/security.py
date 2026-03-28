import pathlib

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
    def validate_project(path_str: str) -> pathlib.Path:
        p = pathlib.Path(path_str).resolve()
        if not p.exists(): raise FileNotFoundError(f"Path does not exist: {path_str}")
        if not p.is_dir(): raise NotADirectoryError(f"Not a directory: {path_str}")
        
        blocked_keywords = {'windows', 'system32', 'program files', 'etc', 'usr', 'bin', 'sbin', 'boot', 'var', 'proc', 'sys', 'root', 'dev'}
        p_resolved = p.resolve()
        path_parts = {part.lower() for part in p_resolved.parts}
        found_blocks = blocked_keywords.intersection(path_parts)

        if len(p.parts) <= 1:
             raise PermissionError("Cannot register root drive as a project.")

        if found_blocks:
            raise PermissionError(f"Access to system directory '{list(found_blocks)[0]}' is blocked for security.")
        return p
