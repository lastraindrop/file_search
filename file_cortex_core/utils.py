import pathlib
import os
import fnmatch
import datetime
from functools import lru_cache
import pathspec
import logging

# Import logger from config to ensure consistency
from .config import logger

class FormatUtils:
    @staticmethod
    def format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    @staticmethod
    def format_datetime(mtime):
        try:
            return datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return ""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Refined token estimation (approx 4 chars/token for code).
        Can be improved in future with BPE or professional libraries.
        """
        if not text: return 0
        return len(text) // 4

class FileUtils:
    @staticmethod
    def is_binary(file_path):
        path = pathlib.Path(file_path)
        try:
            if not path.exists(): return False
            if path.stat().st_size == 0: return False
        except Exception: return True

        text_exts = {'.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.txt', '.yml', '.yaml', '.xml', '.sql', '.c', '.cpp', '.h', '.java', '.go', '.rs', '.sh', '.bat', '.ini', '.cfg', '.toml'}
        if path.suffix.lower() in text_exts:
            return False
            
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(8192)
                if not chunk: return False
                if b'\0' in chunk: return True
                try:
                    chunk.decode('utf-8')
                    return False
                except UnicodeDecodeError:
                    return True
        except Exception as e:
            logger.debug(f"Binary check failed for {file_path}: {e}")
            return True

    @staticmethod
    def clear_cache():
        FileUtils._get_cached_gitignore_spec.cache_clear()

    @staticmethod
    def get_gitignore_spec(root_dir):
        gitignore_path = pathlib.Path(root_dir) / ".gitignore"
        mtime = 0
        if gitignore_path.exists():
            try:
                mtime = gitignore_path.stat().st_mtime
            except: pass
        return FileUtils._get_cached_gitignore_spec(str(root_dir), mtime)

    @staticmethod
    @lru_cache(maxsize=32)
    def _get_cached_gitignore_spec(root_dir, mtime):
        gitignore_path = pathlib.Path(root_dir) / ".gitignore"
        lines = []
        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception as e:
                logger.warning(f"Failed to read gitignore at {gitignore_path}: {e}")
        return pathspec.PathSpec.from_lines('gitwildmatch', lines)

    @staticmethod
    def should_ignore(name: str, rel_path: pathlib.Path, manual_excludes: list[str], git_spec: pathspec.PathSpec | None = None, is_dir: bool = False) -> bool:
        for pattern in manual_excludes:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(str(rel_path), pattern):
                return True
        if git_spec:
            path_str = str(rel_path).replace(os.sep, '/')
            if is_dir and not path_str.endswith('/'):
                path_str += '/'
            if git_spec.match_file(path_str):
                return True
        return False

    @staticmethod
    def get_project_items(root_dir: str, manual_excludes: list[str], use_gitignore: bool = True, mode: str = "files") -> list[str]:
        root = pathlib.Path(root_dir).resolve()
        git_spec = FileUtils.get_gitignore_spec(str(root)) if use_gitignore else None
        results = []

        if mode == "top_folders":
            for item in root.iterdir():
                rel = item.relative_to(root)
                if not FileUtils.should_ignore(item.name, rel, manual_excludes, git_spec, item.is_dir()):
                    results.append(str(item))
        else:
            for curr_root, dirs, files in os.walk(root):
                curr_root_path = pathlib.Path(curr_root)
                dirs[:] = [d for d in dirs if not FileUtils.should_ignore(d, (curr_root_path / d).relative_to(root), manual_excludes, git_spec, True)]
                for f in files:
                    rel = (curr_root_path / f).relative_to(root)
                    if not FileUtils.should_ignore(f, rel, manual_excludes, git_spec, False):
                        results.append(str(curr_root_path / f))
        return results

    @staticmethod
    def get_language_tag(suffix):
        mapping = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.tsx': 'typescript', '.jsx': 'javascript',
            '.html': 'html', '.css': 'css', '.json': 'json', '.md': 'markdown',
            '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.h': 'cpp', '.cs': 'csharp',
            '.rs': 'rust', '.go': 'go', '.sql': 'sql', '.xml': 'xml', '.sh': 'bash',
            '.bat': 'batch', '.yml': 'yaml', '.yaml': 'yaml', '.toml': 'toml',
            '.dockerfile': 'dockerfile', 'dockerfile': 'dockerfile',
            '.vue': 'vue', '.svelte': 'svelte', '.php': 'php', '.rb': 'ruby',
            '.swift': 'swift', '.kt': 'kotlin', '.dart': 'dart',
            '.ini': 'ini', '.cfg': 'ini', '.log': 'text'
        }
        return mapping.get(suffix.lower(), '')

    @staticmethod
    def get_metadata(path_obj):
        try:
            stat = path_obj.stat()
            return {
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "ext": path_obj.suffix.lower()
            }
        except Exception:
            return {"size": 0, "mtime": 0, "ext": ""}

    @staticmethod
    def generate_ascii_tree(root_dir, excludes_str, use_gitignore=True, max_depth=15):
        root_dir = pathlib.Path(root_dir)
        lines = [f"Project: {root_dir.name}"]
        excludes = [e.lower().strip() for e in excludes_str.split() if e.strip()]
        git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None

        def _build_tree(path, prefix="", depth=0):
            if depth > max_depth:
                lines.append(f"{prefix}└── [Max Depth Reached ({max_depth}) ...]")
                return
            try:
                entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
                valid_entries = []
                for entry in entries:
                    rel_path = pathlib.Path(entry.path).relative_to(root_dir)
                    if not FileUtils.should_ignore(entry.name, rel_path, excludes, git_spec):
                        valid_entries.append(entry)
                
                for i, entry in enumerate(valid_entries):
                    is_last = (i == len(valid_entries) - 1)
                    connector = "└── " if is_last else "├── "
                    lines.append(f"{prefix}{connector}{entry.name}")
                    if entry.is_dir():
                        new_prefix = prefix + ("    " if is_last else "│   ")
                        _build_tree(entry.path, new_prefix, depth + 1)
            except PermissionError:
                logger.warning(f"Permission denied: {path}")
            except Exception as e:
                logger.error(f"Tree generation error at {path}: {e}")

        try:
            _build_tree(root_dir)
        except Exception as e:
            logger.error(f"Tree generation failed: {e}")
        return "\n".join(lines)

class ContextFormatter:
    @staticmethod
    def to_markdown(paths, root_dir=None, prompt_prefix=None):
        """
        Converts a list of file paths to a formatted markdown block.
        Optionally includes a prompt prefix at the top.
        """
        blocks = []
        if prompt_prefix:
            blocks.append(f"{prompt_prefix}\n\n---\n\n")
            
        root = pathlib.Path(root_dir).resolve() if root_dir else None
        for p_str in paths:
            p = pathlib.Path(p_str)
            if not p.exists() or not p.is_file() or FileUtils.is_binary(p):
                continue
            try:
                display_name = p.relative_to(root) if root and root in p.resolve().parents else p.name
                stat = p.stat()
                size_kb = stat.st_size / 1024
                
                content = p.read_text('utf-8', 'ignore')
                
                # Feature: Token Noise Reduction (Stub for now, could remove large arrays etc.)
                # content = NoiseReducer.clean(content) 

                lang = FileUtils.get_language_tag(p.suffix)
                header = f"File: {display_name} ({size_kb:.1f} KB)\n"
                blocks.append(f"{header}```{lang}\n{content}\n```\n\n")
            except Exception as e:
                logger.error(f"Failed to format {p_str}: {e}")
        return "".join(blocks)
