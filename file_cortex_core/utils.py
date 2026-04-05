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
    def format_number(val):
        """Format number with thousands separator."""
        try:
            return f"{int(val):,}"
        except (ValueError, TypeError):
            return str(val)

    @staticmethod
    def format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

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
        if not text:
            return 0
        return len(text) // 4

    @staticmethod
    def collect_paths(paths, root_dir=None, mode='relative', separator='\n', file_prefix='', dir_suffix=''):
        """
        Formats a list of paths into a single string with a custom separator.
        """
        # Handle escapes in separator
        sep = separator.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
        
        formatted = []
        root = pathlib.Path(root_dir).resolve() if root_dir else None
        
        for p_str in paths:
            try:
                # We use resolve() to handle '..' and normalize paths first
                p = pathlib.Path(p_str).resolve()
                is_dir = p.is_dir()
                
                final_p_str = ""
                if mode == 'relative' and root:
                    # Check if p is under root
                    if root in p.parents or root == p:
                        final_p_str = str(p.relative_to(root))
                    else:
                        final_p_str = str(p)
                else:
                    final_p_str = str(p)
                
                # Apply symbols
                if is_dir:
                    if dir_suffix and not final_p_str.endswith(dir_suffix):
                        final_p_str += dir_suffix
                
                # Apply common prefix to both files and dirs
                final_p_str = file_prefix + final_p_str
                
                formatted.append(final_p_str)
            except Exception:
                formatted.append(p_str)
                
        return sep.join(formatted)

class FileUtils:
    @staticmethod
    def open_path_in_os(path):
        """Opens a file or directory using the default OS application."""
        import subprocess, sys
        p_str = str(path)
        try:
            if sys.platform == 'win32':
                os.startfile(p_str)
            elif sys.platform == 'darwin':
                subprocess.run(['open', p_str], check=True)
            else:
                subprocess.run(['xdg-open', p_str], check=True)
        except Exception as e:
            logger.error(f"Failed to open path {p_str}: {e}")

    @staticmethod
    def is_binary(file_path):
        path = pathlib.Path(file_path)
        try:
            if not path.exists():
                return False
            if path.stat().st_size == 0:
                return False
        except Exception:
            return True

        # 1. Extension Whitelist (Force Text)
        text_exts = {'.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.txt', '.yml', '.yaml', 
                     '.xml', '.sql', '.c', '.cpp', '.h', '.java', '.go', '.rs', '.sh', '.bat', 
                     '.ini', '.cfg', '.toml', '.log', '.env', '.dockerfile'}
        if path.suffix.lower() in text_exts:
            return False
            
        # 2. Heuristic Byte Scan
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(8192)
                if not chunk:
                    return False
                
                # NULL bytes are a strong indicator of binary (except UTF-16, which is rare for code)
                if b'\0' in chunk: return True
                
                # Count printable vs non-printable (heuristic)
                # We allow for some non-UTF8 noise (e.g. GBK, or random high-bytes)
                non_text_count = 0
                for byte in chunk:
                    if byte < 32 and byte not in (7, 8, 9, 10, 12, 13, 27): # Control chars
                        non_text_count += 1
                
                # If more than 30% are non-text control chars, it's likely binary
                if (non_text_count / len(chunk)) > 0.3:
                    return True
                return False
        except Exception:
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
            except Exception: pass
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
    def flatten_paths(paths: list[str], root_dir: str = None, 
                      manual_excludes: list[str] = None, use_gitignore: bool = True) -> list[str]:
        """
        Expands all directories in the list recursively and returns a unique set of files.
        Applies filtering (gitignore/manual) to exclude unwanted noise.
        """
        if not paths: return []
        unique_files = set()
        root = pathlib.Path(root_dir).resolve() if root_dir else None
        git_spec = FileUtils.get_gitignore_spec(str(root)) if (root and use_gitignore) else None
        excludes = manual_excludes or []
        
        for p_str in paths:
            p = pathlib.Path(p_str).resolve()
            if not p.exists():
                continue
            
            if p.is_file():
                # Direct file addition
                unique_files.add(str(p))
            elif p.is_dir():
                # Recursive folder addition
                for curr_root, dirs, files in os.walk(p):
                    curr_root_path = pathlib.Path(curr_root).resolve()
                    
                    # Filter directories in-place for os.walk efficiency
                    valid_dirs = []
                    for d in dirs:
                        d_path = curr_root_path / d
                        # CR-07 Fix: Handle root == d_path
                        if root == d_path or root in d_path.parents:
                            rel = d_path.relative_to(root) if (root and root in d_path.parents) else d_path
                            if not FileUtils.should_ignore(d, rel, excludes, git_spec, True):
                                valid_dirs.append(d)
                    dirs[:] = valid_dirs
                    
                    for f in files:
                        f_path = curr_root_path / f
                        rel = f_path.relative_to(root) if (root and root in f_path.parents) else f_path
                        if not FileUtils.should_ignore(f, rel, excludes, git_spec, False):
                            unique_files.add(str(f_path))
                            
        return sorted(list(unique_files))

    @staticmethod
    def read_text_smart(file_path: pathlib.Path, max_bytes: int = None) -> str:
        """Reads file content with smart encoding detection (safe for large files).
        
        Args:
            file_path: Path to the file to read.
            max_bytes: Optional. If set, truncates the returned content to approximately
                       this many bytes. Used for preview to prevent OOM.
        """
        try:
            from charset_normalizer import from_bytes
            # Only read header for encoding detection to prevent OOM
            with open(file_path, 'rb') as f:
                header = f.read(65536) # Increased header size for better detection
            
            best_match = from_bytes(header).best()
            # charset-normalizer might return None if no high-confidence match
            if best_match and best_match.encoding:
                encoding = best_match.encoding
            else:
                # Fallback heuristic for common CJK/Legacy encodings if utf-8 fails
                encoding = 'utf-8'
            
            if max_bytes:
                with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                    return f.read(max_bytes)
            return file_path.read_text(encoding=encoding, errors='ignore')
        except Exception as e:
            logger.debug(f"Smart read failed for {file_path}: {e}")
            pass
        # Fallback to utf-8 ignore
        if max_bytes:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(max_bytes)
        return file_path.read_text('utf-8', 'ignore')

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
                with os.scandir(path) as it:
                    entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
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

class NoiseReducer:
    """
    Cleans code context to reduce token noise.
    Filters out minified blocks, extremely long lines, and redundant metadata.
    """
    @staticmethod
    def clean(content: str, max_line_length: int = 500) -> str:
        if content is None:
            return ""
        
        lines = content.splitlines()
        cleaned_lines = []
        is_skipping = False
        
        for line in lines:
            # 1. Skip extremely long lines (likely minified or data chunks)
            if len(line) > max_line_length:
                cleaned_lines.append(f"[... Line of {len(line)} chars skipped by NoiseReducer ...]")
                continue
            
            # 2. Heuristic: skip blocks that look like large base64 (e.g. embedded assets)
            if len(line) > 200 and not any(c.isspace() for c in line):
                # Check if it's mostly base64 chars
                total = len(line)
                alnum = sum(1 for c in line if c.isalnum() or c in '+/=')
                if (alnum / total) > 0.95:
                    cleaned_lines.append(f"[... Base64-like block of {total} chars skipped ...]")
                    continue
            
            cleaned_lines.append(line)
            
        return "\n".join(cleaned_lines)

class ContextFormatter:
    @staticmethod
    def to_markdown(paths: list[str], root_dir: str = None, prompt_prefix: str = None, 
                    manual_excludes: list[str] = None, use_gitignore: bool = True):
        """
        Converts a list of file paths (and directories) to a formatted markdown block.
        Recursively expands directories and de-duplicates files.
        """
        # 1. Flatten and De-duplicate
        all_files = FileUtils.flatten_paths(paths, root_dir, manual_excludes, use_gitignore)
        
        blocks = []
        if prompt_prefix:
            blocks.append(f"{prompt_prefix}\n\n---\n\n")
            
        root = pathlib.Path(root_dir).resolve() if root_dir else None
        
        for f_str in all_files:
            p = pathlib.Path(f_str)
            if not p.exists() or not p.is_file() or FileUtils.is_binary(p):
                continue
            
            try:
                p_res = p.resolve()
                # CR-06 Fix: Handle root == p_res
                rel_path = p_res.relative_to(root) if root and (root == p_res or root in p_res.parents) else p.name
                lang = FileUtils.get_language_tag(p.suffix)
                stat = p.stat()
                size_kb = stat.st_size / 1024
                
                # Use 1MB limit for context files to prevent OOM
                content = FileUtils.read_text_smart(p, max_bytes=1024*1024)
                content = NoiseReducer.clean(content)
                
                header = f"File: {rel_path} ({size_kb:.1f} KB)\n"
                blocks.append(f"{header}```{lang}\n{content}\n```\n\n")
            except Exception as e:
                logger.error(f"Failed to format file {f_str} for context: {e}")
                
        return "".join(blocks)
