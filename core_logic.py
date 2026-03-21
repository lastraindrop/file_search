import pathlib
import os
import json
import fnmatch
import threading
import queue
import re
import pathspec

# --- Data Management ---
def get_app_dir():
    home = pathlib.Path.home()
    app_dir = home / ".ai_context_workbench"
    try:
        app_dir.mkdir(exist_ok=True)
    except: pass
    return app_dir

CONFIG_FILE = get_app_dir() / "config.json"

class DataManager:
    def __init__(self):
        self.data = {"last_directory": "", "projects": {}}
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.data.update(json.load(f))
            except Exception as e: print(f"Config load error: {e}")

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
        except Exception as e: print(f"Config save error: {e}")

    def get_project_data(self, path_str):
        if path_str not in self.data["projects"]:
            self.data["projects"][path_str] = {
                "groups": {"Default": []},
                "current_group": "Default",
                "excludes": ".git .idea __pycache__ venv node_modules .vscode dist build .DS_Store *.pyc *.png *.jpg *.exe *.dll *.so *.dylib .env"
            }
        return self.data["projects"][path_str]

# --- File Utilities ---
class FileUtils:
    @staticmethod
    def is_binary(file_path):
        """Checks if a file is binary by extension or content analysis."""
        path = pathlib.Path(file_path)
        
        # 1. Fast path: Common text extensions
        text_exts = {'.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.txt', '.yml', '.yaml', '.xml', '.sql', '.c', '.cpp', '.h', '.java'}
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
        except: return True

    @staticmethod
    def get_gitignore_spec(root_dir):
        """Compiles a pathspec object from .gitignore if it exists."""
        gitignore_path = pathlib.Path(root_dir) / ".gitignore"
        lines = []
        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except: pass
        return pathspec.PathSpec.from_lines('gitwildmatch', lines)

    @staticmethod
    def should_ignore(name, rel_path, manual_excludes, git_spec=None):
        """
        Determines if a file should be ignored.
        :param name: Filename (e.g., 'test.py')
        :param rel_path: Path relative to project root (e.g., 'src/test.py')
        :param manual_excludes: List of glob patterns to exclude manually
        :param git_spec: pathspec object (optional)
        """
        # 1. Manual Excludes (Glob)
        name_lower = name.lower()
        for ex in manual_excludes:
            if fnmatch.fnmatch(name_lower, ex): return True
        
        # 2. Gitignore (.gitignore)
        if git_spec:
            # pathspec expects unix-style paths for matching
            path_str = str(rel_path).replace(os.sep, '/')
            if git_spec.match_file(path_str):
                return True
                
        return False

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
            '.rs': 'rust', '.swift': 'swift', '.kt': 'kotlin', '.dart': 'dart',
            '.ini': 'ini', '.cfg': 'ini', '.log': 'text'
        }
        return mapping.get(suffix.lower(), '')

    @staticmethod
    def generate_ascii_tree(root_dir, excludes_str, use_gitignore=True):
        root_dir = pathlib.Path(root_dir)
        lines = [f"Project: {root_dir.name}"]
        excludes = [e.lower().strip() for e in excludes_str.split() if e.strip()]
        git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None

        def _build_tree(path, prefix=""):
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
                        _build_tree(entry.path, new_prefix)
            except PermissionError: pass
            except Exception: pass

        _build_tree(root_dir)
        return "\n".join(lines)

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

# --- Search Logic (Generator-based) ---
def search_generator(root_dir, search_text, search_mode, manual_excludes, 
                     include_dirs=False, use_gitignore=True, 
                     is_inverse=False, case_sensitive=False):
    """
    Yields (path_str, match_type_str) tuples.
    """
    root_dir = pathlib.Path(root_dir)
    excludes = [e.lower().strip() for e in manual_excludes.split() if e.strip()]
    git_spec = FileUtils.get_gitignore_spec(root_dir) if use_gitignore else None
    
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

    def match_content(path):
        if search_mode not in ('content', 'regex') or not search_text: return False
        
        try:
            if path.stat().st_size > 5 * 1024 * 1024: return False
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
        except Exception: return False

    for root, dirs, files in os.walk(root_dir):
        rel_root = pathlib.Path(root).relative_to(root_dir)
        
        # Pythonic filtering of directories to prevent recursion
        dirs[:] = [d for d in dirs if not FileUtils.should_ignore(d, rel_root / d, excludes, git_spec)]
        
        if include_dirs:
            for d in dirs:
                if match_name(d):
                    yield (str(pathlib.Path(root) / d), "📁 Folder")

        for file in files:
            full_path = pathlib.Path(root) / file
            rel_path = rel_root / file
            
            if FileUtils.should_ignore(file, rel_path, excludes, git_spec):
                continue

            # 1. Check Name Match
            if search_mode != 'content':
                if match_name(file):
                    yield (str(full_path), "Inverse Match" if is_inverse else "Match")
                    continue
            
            # 2. Check Content Match
            if search_mode in ('content', 'regex') and match_content(full_path):
                 yield (str(full_path), "Inverse Content" if is_inverse else "Content Match")


class SearchWorker(threading.Thread):
    """
    Thread wrapper for the search generator (for Tkinter).
    """
    def __init__(self, root_dir, search_text, search_mode, manual_excludes, 
                 include_dirs, result_queue, stop_event, use_gitignore=True,
                 is_inverse=False, case_sensitive=False):
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
        self.daemon = True

    def run(self):
        gen = search_generator(self.root_dir, self.search_text, self.search_mode, 
                               self.manual_excludes, self.include_dirs, self.use_gitignore,
                               self.is_inverse, self.case_sensitive)
        if gen is None:
            self.result_queue.put(("DONE", "DONE"))
            return

        for result in gen:
            if self.stop_event.is_set(): break
            self.result_queue.put(result)
        
        self.result_queue.put(("DONE", "DONE"))