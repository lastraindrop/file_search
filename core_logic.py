import pathlib
import os
import json
import fnmatch
import threading
import queue
import re
import pathspec
import logging
from functools import lru_cache
# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FileCortex")

# --- Data Management ---
def get_app_dir() -> pathlib.Path:
    home = pathlib.Path.home()
    app_dir = home / ".filecortex"
    try:
        app_dir.mkdir(exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create app directory: {e}")
    return app_dir

# --- Security & Validation ---
class PathValidator:
    @staticmethod
    def is_safe(target_path, root_path):
        """Strict check to prevent path traversal outside project root."""
        try:
            target = pathlib.Path(target_path).resolve()
            root = pathlib.Path(root_path).resolve()
            # Use is_relative_to (Python 3.9+) for more robust checking
            if hasattr(target, 'is_relative_to'):
                 return target.is_relative_to(root)
            # Fallback for older versions if needed, though 3.9+ is expected
            return root == target or root in target.parents
        except Exception:
            return False

    @staticmethod
    def validate_project(path_str: str) -> pathlib.Path:
        p = pathlib.Path(path_str).resolve()
        if not p.exists(): raise FileNotFoundError(f"Path does not exist: {path_str}")
        if not p.is_dir(): raise NotADirectoryError(f"Not a directory: {path_str}")
        
        # Block system directories
        blocked_keywords = {'windows', 'system32', 'program files', 'etc', 'usr/bin', 'usr/sbin', 'boot', 'var', 'proc', 'sys', 'root', 'dev'}
        
        # Exact path components check to avoid substrings matching innocent directories
        path_parts = {part.lower() for part in p.parts}
        found_blocks = blocked_keywords.intersection(path_parts)

        # Check if it's a drive root (e.g., C:/)
        if len(p.parts) <= 1:
             raise PermissionError("Cannot register root drive as a project.")

        if found_blocks:
            raise PermissionError(f"Access to system directory '{list(found_blocks)[0]}' is blocked for security.")
        return p

class FormatUtils:
    @staticmethod
    def format_size(size_bytes):
        """Returns human-readable file size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    @staticmethod
    def format_datetime(mtime):
        """Returns formatted modification time."""
        import datetime
        try:
            return datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        except:
            return ""

CONFIG_FILE = get_app_dir() / "config.json"

class DataManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DataManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        self.data = {"last_directory": "", "projects": {}}
        self.load()
        self._initialized = True

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.data.update(json.load(f))
            except Exception as e:
                logger.error(f"Config load error: {e}")

    def save(self):
        try:
            temp_file = CONFIG_FILE.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, CONFIG_FILE)
        except Exception as e:
            logger.error(f"Config save error: {e}")

    def get_project_data(self, path_str: str) -> dict:
        DEFAULT_SCHEMA = {
            "groups": {"Default": []},
            "current_group": "Default",
            "excludes": ".git .idea __pycache__ venv node_modules .vscode dist build .DS_Store *.pyc *.png *.jpg *.exe *.dll *.so *.dylib .env",
            "max_search_size_mb": 5,
            "notes": {},
            "tags": {},
            "sessions": [],
            "staging_list": [],
            "quick_categories": {}, # {Name: Relative_Target_Dir}
            "custom_tools": {}      # {Name: Command_Template}
        }
        
        # Ensure path_str is canonical for key lookup
        try:
            path_key = str(pathlib.Path(path_str).resolve())
        except:
            path_key = path_str

        if path_key not in self.data["projects"]:
            self.data["projects"][path_key] = DEFAULT_SCHEMA.copy()
        else:
            proj = self.data["projects"][path_key]
            for key, val in DEFAULT_SCHEMA.items():
                if key not in proj:
                    proj[key] = val
        return self.data["projects"][path_key]

    def batch_stage(self, project_path: str, paths: list[str]) -> int:
        proj = self.get_project_data(project_path)
        added_count = 0
        for p in paths:
            if p not in proj["staging_list"]:
                proj["staging_list"].append(p)
                added_count += 1
        if added_count > 0:
            self.save()
        return added_count

    def resolve_project_root(self, target_path_str: str) -> str | None:
        """
        Identifies which registered project contains the given path.
        Returns the canonical project root path string or None.
        """
        try:
            target = pathlib.Path(target_path_str).resolve()
            for p_root in self.data["projects"]:
                root = pathlib.Path(p_root).resolve()
                if target == root or root in target.parents:
                    return str(root)
        except Exception:
            pass
        return None

    def add_note(self, project_path, file_path, note):
        proj = self.get_project_data(project_path)
        proj["notes"][file_path] = note
        self.save()

    def add_tag(self, project_path, file_path, tag):
        proj = self.get_project_data(project_path)
        if file_path not in proj["tags"]: proj["tags"][file_path] = []
        if tag not in proj["tags"][file_path]: proj["tags"][file_path].append(tag)
        self.save()

    def remove_tag(self, project_path, file_path, tag):
        proj = self.get_project_data(project_path)
        if file_path in proj["tags"] and tag in proj["tags"][file_path]:
            proj["tags"][file_path].remove(tag)
        self.save()

    def save_session(self, project_path, session_data):
        """Saves a snapshot of current workspace state."""
        proj = self.get_project_data(project_path)
        # Keep only last 5 sessions
        proj["sessions"].insert(0, session_data)
        proj["sessions"] = proj["sessions"][:5]
        self.save()

    def update_project_settings(self, project_path, settings: dict):
        """Updates project-level settings (excludes, search preferences)."""
        proj = self.get_project_data(project_path)
        for k, v in settings.items():
            proj[k] = v
        self.save()

    def add_to_group(self, project_path, group_name, file_paths):
        """Adds a list of files to a specific group (favorites)."""
        proj = self.get_project_data(project_path)
        if group_name not in proj["groups"]:
            proj["groups"][group_name] = []
        for path in file_paths:
            if path not in proj["groups"][group_name]:
                proj["groups"][group_name].append(path)
        self.save()

    def remove_from_group(self, project_path, group_name, file_paths):
        """Removes a list of files from a specific group."""
        proj = self.get_project_data(project_path)
        if group_name in proj["groups"]:
            for path in file_paths:
                if path in proj["groups"][group_name]:
                    proj["groups"][group_name].remove(path)
            self.save()

# --- File Utilities ---
class FileUtils:
    @staticmethod
    def open_path_in_os(path_str):
        import sys, subprocess
        if sys.platform == 'win32':
            os.startfile(path_str)
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(path_str)], check=False)
        else:
            subprocess.run(['xdg-open', str(path_str)], check=False)

    @staticmethod
    def is_binary(file_path):
        """Checks if a file is binary by extension or content analysis."""
        path = pathlib.Path(file_path)
        
        # 0. Handle non-existent or zero-byte files
        try:
            if not path.exists(): return False
            if path.stat().st_size == 0: return False # Empty files are text-safe
        except Exception: return True # Locked or inaccessible

        # 1. Fast path: Common text extensions
        text_exts = {'.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.txt', '.yml', '.yaml', '.xml', '.sql', '.c', '.cpp', '.h', '.java', '.go', '.rs', '.sh', '.bat', '.ini', '.cfg', '.toml'}
        if path.suffix.lower() in text_exts:
            return False
            
        # 2. Content analysis
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(8192)
                if not chunk: return False
                if b'\0' in chunk: return True  # Binary usually contains null bytes
                try:
                    chunk.decode('utf-8')
                    return False
                except UnicodeDecodeError:
                    return True
        except Exception as e:
            logger.debug(f"Binary check failed for {file_path}: {e}")
            return True

    @staticmethod
    def get_gitignore_spec(root_dir):
        """Public interface for cached gitignore spec."""
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
        """Internal cached method, mtime ensures cache invalidation on file change."""
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
    def clear_cache():
        """Clears the gitignore spec cache."""
        FileUtils._get_cached_gitignore_spec.cache_clear()

    @staticmethod
    def should_ignore(name: str, rel_path: pathlib.Path, manual_excludes: list[str], git_spec: pathspec.PathSpec | None = None, is_dir: bool = False) -> bool:
        """
        Comprehensive check against manual excludes and gitignore patterns.
        :param name: Filename (e.g., 'test.py')
        :param rel_path: Path relative to project root (e.g., 'src/test.py')
        :param manual_excludes: List of glob patterns to exclude manually
        :param git_spec: pathspec object (optional)
        :param is_dir: Boolean indicating if the item is a directory
        """
        # 1. Manual check
        for pattern in manual_excludes:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(str(rel_path), pattern):
                return True
        # 2. Gitignore check
        if git_spec:
            path_str = str(rel_path).replace(os.sep, '/')
            if is_dir and not path_str.endswith('/'):
                path_str += '/'
            if git_spec.match_file(path_str):
                return True
        return False

    @staticmethod
    def get_project_items(root_dir: str, manual_excludes: list[str], use_gitignore: bool = True, mode: str = "files") -> list[str]:
        """
        Scans project directory for items to stage.
        :param mode: 'files' (recursive files) or 'top_folders' (items in root)
        """
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
        """Returns the markdown language tag for a given file extension."""
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
    def get_tool_suggestions(path_str, tool_rules):
        """Returns a list of suggested tool names based on file pattern rules."""
        import fnmatch
        name = pathlib.Path(path_str).name
        suggestions = []
        for pattern, tools in tool_rules.items():
            if fnmatch.fnmatch(name, pattern):
                suggestions.extend(tools)
        return list(set(suggestions))

    @staticmethod
    def get_metadata(path_obj):
        """Returns size, mtime, and extension for a path."""
        try:
            stat = path_obj.stat()
            return {
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "ext": path_obj.suffix.lower()
            }
        except:
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
                # Sort: directories first, then files
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
    def to_markdown(paths, root_dir=None):
        """Converts a list of file paths to a formatted markdown block with metadata."""
        blocks = []
        for p_str in paths:
            p = pathlib.Path(p_str)
            if not p.exists() or not p.is_file() or FileUtils.is_binary(p):
                continue
            try:
                # Use relative path if root_dir is provided
                display_name = p.relative_to(root_dir) if root_dir and root_dir in p.parents else p.name
                
                # Get metadata
                stat = p.stat()
                size_kb = stat.st_size / 1024
                
                content = p.read_text('utf-8', 'ignore')
                lang = FileUtils.get_language_tag(p.suffix)
                
                # Enhanced format with metadata header
                header = f"File: {display_name} ({size_kb:.1f} KB)\n"
                blocks.append(f"{header}```{lang}\n{content}\n```\n\n")
            except Exception as e:
                logger.error(f"Failed to format {p_str}: {e}")
        return "".join(blocks)

# --- File Operations (Safe Handlers) ---
class FileOps:
    @staticmethod
    def rename_file(old_path_str, new_name):
        old_path = pathlib.Path(old_path_str)
        if not old_path.exists(): raise FileNotFoundError("Target path does not exist.")
        new_path = old_path.parent / new_name
        if new_path.exists(): raise FileExistsError("A file with new name already exists.")
        old_path.rename(new_path)
        return str(new_path)

    @staticmethod
    def delete_file(path_str):
        path = pathlib.Path(path_str)
        if not path.exists(): raise FileNotFoundError("Target path does not exist.")
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            import shutil
            shutil.rmtree(path)
        return True

    @staticmethod
    def move_file(src_path_str, dst_dir_str):
        src_path = pathlib.Path(src_path_str)
        dst_dir = pathlib.Path(dst_dir_str)
        if not src_path.exists(): raise FileNotFoundError("Source path does not exist.")
        if not dst_dir.exists() or not dst_dir.is_dir(): raise FileNotFoundError("Destination directory does not exist.")
        
        dst_path = dst_dir / src_path.name
        if dst_path.exists(): raise FileExistsError("A file with same name exists in destination.")
        
        import shutil
        shutil.move(str(src_path), str(dst_path))
        return str(dst_path)

    @staticmethod
    def save_content(path_str, content):
        path = pathlib.Path(path_str)
        if not path.exists(): raise FileNotFoundError("Target file does not exist.")
        if not path.is_file(): raise IsADirectoryError("Target is a directory.")
        if FileUtils.is_binary(path): raise ValueError("Cannot save binary file as text.")
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True

    @staticmethod
    def create_item(parent_path_str, name, is_dir=False):
        parent_path = pathlib.Path(parent_path_str)
        if not parent_path.exists() or not parent_path.is_dir():
            raise FileNotFoundError("Parent directory does not exist.")
        
        new_path = parent_path / name
        if new_path.exists():
            raise FileExistsError(f"{'Directory' if is_dir else 'File'} already exists.")
        
        if is_dir:
            new_path.mkdir()
        else:
            new_path.touch()
        return str(new_path)

    @staticmethod
    def archive_selection(paths, output_path_str, root_dir=None):
        import zipfile
        output_path = pathlib.Path(output_path_str)
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for p_str in paths:
                p = pathlib.Path(p_str)
                if not p.exists(): continue
                
                # If root_dir is provided, use it for relative paths in zip
                arcname = p.relative_to(root_dir) if root_dir and root_dir in p.parents else p.name
                
                if p.is_file():
                    zipf.write(p, arcname)
                elif p.is_dir():
                    for root, _, files in os.walk(p):
                        for file in files:
                            full_f = pathlib.Path(root) / file
                            # Maintain structure relative to root_dir or parent of p
                            rel_base = root_dir if root_dir else p.parent
                            zipf.write(full_f, full_f.relative_to(rel_base))
        return str(output_path)
    
    @staticmethod
    def batch_categorize(project_path, paths, category_name):
        """Moves a list of files to a predefined category directory."""
        data_mgr = DataManager()
        proj = data_mgr.get_project_data(project_path)
        cat_dir_rel = proj["quick_categories"].get(category_name)
        if not cat_dir_rel:
            raise ValueError(f"Category '{category_name}' not defined.")
        
        root = pathlib.Path(project_path)
        target_dir = (root / cat_dir_rel).resolve()
        
        # Security Check
        if not PathValidator.is_safe(target_dir, root):
            raise PermissionError("Category target directory is outside the workspace.")
        
        if not target_dir.exists():
            target_dir.mkdir(parents=True)
            
        moved = []
        for p_str in paths:
            try:
                # move_file handles safety of src_path and exists checks
                new_p = FileOps.move_file(p_str, str(target_dir))
                moved.append(new_p)
            except Exception as e:
                logger.error(f"Failed to categorize {p_str}: {e}")
        return moved

class ActionBridge:
    @staticmethod
    def execute_tool(template, path_str, project_root):
        """Executes a command template safely on a given path using list-based arguments."""
        p = pathlib.Path(path_str)
        if not p.exists(): return {"error": "Path does not exist"}
        
        # Context extraction
        context = {
            "path": str(p),
            "name": p.name,
            "ext": p.suffix,
            "root": str(project_root),
            "parent": str(p.parent)
        }
        
        try:
            import subprocess
            import shlex
            
            if os.name == 'nt':
                # On Windows, shell=True is more compatible for complex templates
                # but we MUST manually quote context variables to prevent injection.
                def win_quote(s):
                    return f'"{s}"'
                
                safe_context = {k: win_quote(v) for k, v in context.items()}
                cmd_str = template.format(**safe_context)
                
                logger.info(f"AUDIT - Executing external tool (Win/Shell): {cmd_str}")
                res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, check=False)
            else:
                # On Unix/Linux, shell=False with shlex is preferred
                tokens = shlex.split(template, posix=True)
                final_cmd = [t.format(**context) for t in tokens]
                
                logger.info(f"AUDIT - Executing external tool (Unix/List): {' '.join(final_cmd)}")
                res = subprocess.run(final_cmd, shell=False, capture_output=True, text=True, check=False)
                
            return {"stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode}
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {"error": str(e)}

    @staticmethod
    def stream_tool(template, path_str, project_root):
        """Generates real-time output from a command execution."""
        p = pathlib.Path(path_str)
        if not p.exists():
            yield {"error": "Path does not exist"}
            return
        
        context = {
            "path": str(p),
            "name": p.name,
            "ext": p.suffix,
            "root": str(project_root),
            "parent": str(p.parent)
        }
        
        try:
            import shlex
            import subprocess
            
            tokens = shlex.split(template, posix=(os.name != 'nt'))
            final_cmd = [t.format(**context) for t in tokens]
            
            logger.info(f"AUDIT - Streaming external tool: {' '.join(final_cmd)}")
            
            # Start process with piped output
            process = subprocess.Popen(
                final_cmd, 
                shell=False, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, # Merge stderr into stdout for simple streaming
                text=True, 
                bufsize=1, # Line buffered
                encoding='utf-8',
                errors='replace'
            )
            
            # Yield output line by line
            for line in process.stdout:
                yield {"out": line}
            
            process.wait()
            yield {"exit_code": process.returncode}
            
        except Exception as e:
            logger.error(f"Tool streaming failed: {e}")
            yield {"error": str(e)}

# --- Search Logic (Generator-based) ---
def search_generator(root_dir, search_text, search_mode, manual_excludes, 
                     include_dirs=False, use_gitignore=True, 
                     is_inverse=False, case_sensitive=False, max_results=2000):
    """
    Yields dicts with keys: path, match_type, size, mtime, ext.
    """
    root_dir = pathlib.Path(root_dir)
    excludes = [e.lower().strip() for e in manual_excludes.split() if e.strip()]
    git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None
    
    count = 0
    
    search_text_processed = search_text.strip() if case_sensitive else search_text.lower().strip()
    keywords = search_text_processed.split()
    
    # Pre-compile regex if needed
    re_obj = None
    if search_mode == 'regex' and search_text.strip():
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            re_obj = re.compile(search_text, flags)
        except re.error:
            return  # Invalid regex, stop search

    def match_name(name):
        if not search_text: return True != is_inverse
        target = name if case_sensitive else name.lower()
        
        found = False
        if search_mode == 'smart':
            found = all(k in target for k in keywords)
        elif search_mode == 'exact':
            found = search_text_processed in target
        elif search_mode == 'regex' and re_obj:
            found = re_obj.search(name) is not None
            
        return found != is_inverse

    # Get size limit from project config if possible, else 5MB
    size_limit_mb = 5
    if git_spec: # We can use git_spec's existence as a proxy for 'within a project'
        # In a real scenario, we'd pass the config down, 
        # but for now let's use a reasonable default if not specifically passed.
        pass
    
    def match_content(path):
        if search_mode not in ('content', 'regex') or not search_text: return False
        
        try:
            # Configurable limit check
            limit = size_limit_mb * 1024 * 1024
            if path.stat().st_size > limit: return False
            if FileUtils.is_binary(path): return False
            
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    found = False
                    if search_mode == 'regex' and re_obj:
                        found = re_obj.search(line) is not None
                    elif search_mode == 'content':
                        line_to_check = line if case_sensitive else line.lower()
                        found = search_text_processed in line_to_check
                    
                    if found: return True != is_inverse
            return False != is_inverse
        except PermissionError:
            logger.debug(f"Permission denied for content match: {path}")
            return False
        except Exception as e:
            logger.debug(f"Content match error for {path}: {e}")
            return False

    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # We will use a small pool for content matching to avoid I/O saturation
    # but still gain from parallel CPU processing (regex/search)
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        content_futures = {}

        for root, dirs, files in os.walk(root_dir):
            rel_root = pathlib.Path(root).relative_to(root_dir)
            
            # Pythonic filtering of directories to prevent recursion
            dirs[:] = [d for d in dirs if not FileUtils.should_ignore(d, rel_root / d, excludes, git_spec, is_dir=True)]
            
            if include_dirs:
                for d in dirs:
                    if match_name(d):
                        full_d = pathlib.Path(root) / d
                        meta = FileUtils.get_metadata(full_d)
                        yield {
                            "path": str(full_d),
                            "match_type": "📁 Folder",
                            **meta
                        }

            for file in files:
                full_path = pathlib.Path(root) / file
                rel_path = rel_root / file
                
                if FileUtils.should_ignore(file, rel_path, excludes, git_spec, is_dir=False):
                    continue

                # Metadata for the file
                meta = FileUtils.get_metadata(full_path)

                # 1. Check Name Match
                if search_mode != 'content':
                    if match_name(file):
                        count += 1
                        yield {
                            "path": str(full_path),
                            "match_type": "Inverse Match" if is_inverse else "Match",
                            **meta
                        }
                        if count >= max_results: break
                        continue
                
                # 2. Check Content Match (Queued for parallel processing)
                if search_mode in ('content', 'regex') and search_text:
                    future = executor.submit(match_content, full_path)
                    content_futures[future] = {
                        "path": str(full_path),
                        "is_inverse": is_inverse,
                        **meta
                    }
                    
                    # Adaptive Batching: Yield if we have enough results or after a short timeout
                    if len(content_futures) >= 20:
                        # Process completed futures
                        batch = [f for f in content_futures if f.done()]
                        if not batch: # If none are done, wait briefly for at least one
                            try:
                                next(as_completed(content_futures, timeout=0.05))
                                batch = [f for f in content_futures if f.done()]
                            except: pass
                            
                        for f in batch:
                            try:
                                is_match = f.result()
                                info = content_futures.pop(f)
                                if is_match:
                                    count += 1
                                    yield {
                                        "path": info["path"],
                                        "match_type": "Inverse Content" if info["is_inverse"] else "Content Match",
                                        "size": info["size"],
                                        "mtime": info["mtime"],
                                        "ext": info["ext"]
                                    }
                                    if count >= max_results: break
                            except Exception:
                                if f in content_futures: content_futures.pop(f)
                        if count >= max_results: break
                
                if count >= max_results: break
            if count >= max_results: break

        # Final flush of remaining futures
        for f in as_completed(content_futures):
            if count >= max_results: break
            try:
                is_match = f.result()
                info = content_futures.pop(f)
                if is_match:
                    count += 1
                    yield {
                        "path": info["path"],
                        "match_type": "Inverse Content" if info["is_inverse"] else "Content Match",
                        "size": info["size"],
                        "mtime": info["mtime"],
                        "ext": info["ext"]
                    }
            except Exception:
                pass


class SearchWorker(threading.Thread):
    """
    Thread wrapper for the search generator (for Tkinter).
    """
    def __init__(self, root_dir, search_text, search_mode, manual_excludes, 
                 include_dirs, result_queue, stop_event, use_gitignore=True,
                 is_inverse=False, case_sensitive=False, max_results=2000):
        super().__init__()
        self.root_dir = root_dir
        self.search_text = search_text
        self.search_mode = search_mode
        self.manual_excludes = manual_excludes
        self.include_dirs = include_dirs
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.use_gitignore = use_gitignore
        self.is_inverse = is_inverse
        self.case_sensitive = case_sensitive
        self.max_results = max_results
        self.daemon = True

    def run(self):
        gen = search_generator(self.root_dir, self.search_text, self.search_mode, 
                               self.manual_excludes, self.include_dirs, self.use_gitignore,
                               self.is_inverse, self.case_sensitive, self.max_results)
        if gen is None:
            self.result_queue.put(("DONE", "DONE"))
            return

        for result in gen:
            if self.stop_event.is_set(): break
            self.result_queue.put(result)

        self.result_queue.put(("DONE", "DONE"))