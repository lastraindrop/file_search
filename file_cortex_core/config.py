import pathlib
import os
import json
import threading
import logging
import copy

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FileCortex")

def get_app_dir() -> pathlib.Path:
    home = pathlib.Path.home()
    app_dir = home / ".filecortex"
    try:
        app_dir.mkdir(exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create app directory: {e}")
    return app_dir

_CONFIG_FILE = None

def _get_config_file():
    global _CONFIG_FILE
    if _CONFIG_FILE is None:
        _CONFIG_FILE = get_app_dir() / "config.json"
    return _CONFIG_FILE

class DataManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DataManager, cls).__new__(cls)
                cls._instance._init_data()
            return cls._instance

    def __init__(self):
        pass # Initialization handled in __new__ to prevent race conditions

    def _init_data(self):
        self.data = {
            "last_directory": "", 
            "projects": {}, 
            "recent_projects": [], 
            "pinned_projects": []
        }
        self.load()

    def load(self):
        """Loads configuration from the disk and merges with default schema."""
        with self._lock:
            config_file = _get_config_file()
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    # Deep merge: preserve top-level structure, overwrite values
                    self.data["last_directory"] = loaded.get("last_directory", "")
                    if "projects" in loaded:
                        # Defensive: clean legacy non-canonical keys
                        from .security import PathValidator
                        for k, v in list(loaded["projects"].items()):
                            try:
                                norm_k = PathValidator.norm_path(k)
                                self.data["projects"][norm_k] = v
                            except Exception:
                                self.data["projects"][k] = v
                    
                    self.data["recent_projects"] = loaded.get("recent_projects", [])
                    self.data["pinned_projects"] = loaded.get("pinned_projects", [])
                except Exception as e:
                    logger.error(f"Config load error: {e}")

    def save(self):
        """Atomically saves the current configuration to disk."""
        with self._lock:
            # Audit: track save state
            logger.debug(f"Config Save: Persisting {len(self.data['projects'])} projects.")
            # Note: Aggressive re-normalization is removed from save() 
            # to preserve memory references (v). 
            # Normalization is now enforced at all entry points (get_project_data, load).
            data_to_save = copy.deepcopy(self.data)

        config_file = _get_config_file()
        try:
            temp_file = config_file.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, config_file)
        except Exception as e:
            logger.error(f"Config save error: {e}")

    DEFAULT_SCHEMA = {
        "excludes": ".git .idea __pycache__ venv node_modules .vscode dist build .DS_Store *.pyc *.png *.jpg *.exe *.dll *.so *.dylib .env .cache",
        "max_search_size_mb": 10,
        "staging_list": [],
        "current_group": "Default",
        "groups": {"Default": []},
        "notes": {},
        "tags": {},
        "sessions": [],
        "custom_tools": {
             "Summary": "python -c \"import sys; print(f'Summary for {sys.argv[1]}')\" {path}",
             "Lint": "python -m py_compile {path}"
        },
        "quick_categories": {
             "Scripts": "scripts",
             "Docs": "docs"
        },
        "prompt_templates": {
            "Code Review": "Please review the following code for logic errors, potential bugs, and code style. Focus on security and performance. {files}",
            "Summary": "Please provide a concise summary of the functionality and purpose of each of the following files. {files}",
            "Docstring": "Generate professional docstrings for all functions and classes in these files. {files}"
        },
        "search_settings": {
            "mode": "smart",
            "case_sensitive": False,
            "inverse": False,
            "include_dirs": False
        }
    }

    def add_to_recent(self, path: str):
        """Adds a project path to the top of recent projects list."""
        from .security import PathValidator
        try:
            p = PathValidator.norm_path(path)
        except:
            p = path
            
        if p in self.data["recent_projects"]:
            self.data["recent_projects"].remove(p)
        self.data["recent_projects"].insert(0, p)
        # Limit to 15 recent projects
        self.data["recent_projects"] = self.data["recent_projects"][:15]
        self.data["last_directory"] = p
        self.save()

    def toggle_pinned(self, path: str):
        """Toggles the pinned status of a project."""
        from .security import PathValidator
        try:
            p = PathValidator.norm_path(path)
        except Exception:
            p = path
            
        if p in self.data["pinned_projects"]:
            self.data["pinned_projects"].remove(p)
            status = False
        else:
            self.data["pinned_projects"].append(p)
            status = True
        self.save()
        return status

    def get_workspaces_summary(self) -> dict:
        """Returns a categorized summary of workspaces."""
        return {
            "pinned": [{"path": p, "name": pathlib.Path(p).name} for p in self.data["pinned_projects"] if os.path.exists(p)],
            "recent": [{"path": p, "name": pathlib.Path(p).name} for p in self.data["recent_projects"] if os.path.exists(p) and p not in self.data["pinned_projects"]]
        }

    def get_project_data(self, path_str: str) -> dict:
        """Returns (and initializes if needed) the configuration for a given project."""
        from .security import PathValidator
        try:
            path_key = PathValidator.norm_path(path_str)
            logger.debug(f"Config Access: Request='{path_str}' -> Key='{path_key}'")
        except Exception:
            path_key = path_str
            
        if path_key not in self.data["projects"]:
            self.data["projects"][path_key] = copy.deepcopy(self.DEFAULT_SCHEMA)
        else:
            proj = self.data["projects"][path_key]
            for key, val in self.DEFAULT_SCHEMA.items():
                if key not in proj:
                    proj[key] = copy.deepcopy(val)
        
        return self.data["projects"][path_key]

    def batch_stage(self, project_path: str, paths: list[str]) -> int:
        """Adds multiple paths to the staging list atomically."""
        from .security import PathValidator
        proj = self.get_project_data(project_path)
        added_count = 0
        for raw_p in paths:
            p = PathValidator.norm_path(raw_p)
            if p not in proj["staging_list"]:
                proj["staging_list"].append(p)
                added_count += 1
        self.save()
        return added_count

    def resolve_project_root(self, target_path_str: str) -> str | None:
        """Determines if a given path belongs to any registered project root."""
        from .security import PathValidator
        try:
            target = PathValidator.norm_path(target_path_str)
            for p_root in self.data["projects"]:
                # p_root is already normalized on save/load
                if target == p_root or target.startswith(p_root.rstrip('/') + '/'):
                    return p_root
        except Exception:
            pass
        return None

    def add_note(self, project_path, file_path, note):
        proj = self.get_project_data(project_path)
        proj["notes"][file_path] = note
        self.save()

    def add_tag(self, project_path, file_path, tag):
        proj = self.get_project_data(project_path)
        if file_path not in proj["tags"]:
            proj["tags"][file_path] = []
        if tag not in proj["tags"][file_path]:
            proj["tags"][file_path].append(tag)
        self.save()

    def remove_tag(self, project_path, file_path, tag):
        proj = self.get_project_data(project_path)
        if file_path in proj["tags"] and tag in proj["tags"][file_path]:
            proj["tags"][file_path].remove(tag)
        self.save()

    def save_session(self, project_path, session_data):
        proj = self.get_project_data(project_path)
        proj["sessions"].insert(0, session_data)
        proj["sessions"] = proj["sessions"][:5]
        self.save()

    # Whitelist of fields that can be updated via the general settings API.
    # custom_tools and quick_categories are NOT here — they have dedicated APIs
    # to prevent RCE via config injection.
    MUTABLE_SETTINGS = frozenset({
        "excludes", "max_search_size_mb", "staging_list", "current_group",
        "prompt_templates"
    })

    def update_project_settings(self, project_path, settings: dict):
        from .security import PathValidator
        proj = self.get_project_data(project_path)
        for k, v in settings.items():
            if k in self.MUTABLE_SETTINGS:
                if k == "staging_list" and isinstance(v, list):
                    proj[k] = [PathValidator.norm_path(p) for p in v]
                else:
                    proj[k] = v
            else:
                logger.warning(f"Blocked attempt to modify protected key via settings API: {k}")
        self.save()

    def update_custom_tools(self, project_path: str, tools: dict):
        """Dedicated API for updating custom_tools. Validates template format."""
        proj = self.get_project_data(project_path)
        # Basic validation: tools must be a dict of str->str
        if not isinstance(tools, dict):
            raise ValueError("Tools must be a dict of name -> command template")
        for name, template in tools.items():
            if not isinstance(name, str) or not isinstance(template, str):
                raise ValueError(f"Invalid tool entry: {name}")
        proj["custom_tools"] = tools
        self.save()

    def update_quick_categories(self, project_path: str, categories: dict):
        """Dedicated API for updating quick_categories. Validates relative paths."""
        proj = self.get_project_data(project_path)
        if not isinstance(categories, dict):
            raise ValueError("Categories must be a dict of name -> relative_dir")
        for name, rel_dir in categories.items():
            if not isinstance(name, str) or not isinstance(rel_dir, str):
                raise ValueError(f"Invalid category entry: {name}")
            # Block path traversal in category targets
            if '..' in rel_dir:
                raise ValueError(f"Category target must not contain '..': {rel_dir}")
        proj["quick_categories"] = categories
        self.save()

    def add_to_group(self, project_path, group_name, file_paths):
        from .security import PathValidator
        proj = self.get_project_data(project_path)
        if group_name not in proj["groups"]:
            proj["groups"][group_name] = []
        for raw_p in file_paths:
            p = PathValidator.norm_path(raw_p)
            if p not in proj["groups"][group_name]:
                proj["groups"][group_name].append(p)
        self.save()

    def remove_from_group(self, project_path, group_name, file_paths):
        proj = self.get_project_data(project_path)
        if group_name in proj["groups"]:
            for path in file_paths:
                if path in proj["groups"][group_name]:
                    proj["groups"][group_name].remove(path)
            self.save()
