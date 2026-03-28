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
        with self._lock:
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        self.data.update(json.load(f))
                except Exception as e:
                    logger.error(f"Config load error: {e}")

    def save(self):
        with self._lock:
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
            "custom_tools": {},      # {Name: Command_Template}
            "prompt_templates": {    # Feature: Prompt Assembly Base
                "Code Review": "Please review the following code for logic errors, potential bugs, and code style. Focus on security and performance.",
                "Unit Test": "Please write comprehensive unit tests for the following code using a suitable testing framework.",
                "Summary": "Please provide a concise summary of the functionality and purpose of each of the following files."
            }
        }
        
        # Ensure path_str is canonical for key lookup
        try:
            path_key = str(pathlib.Path(path_str).resolve())
        except:
            path_key = path_str

        if path_key not in self.data["projects"]:
            self.data["projects"][path_key] = copy.deepcopy(DEFAULT_SCHEMA)
        else:
            proj = self.data["projects"][path_key]
            for key, val in DEFAULT_SCHEMA.items():
                if key not in proj:
                    proj[key] = copy.deepcopy(val)
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
        proj = self.get_project_data(project_path)
        proj["sessions"].insert(0, session_data)
        proj["sessions"] = proj["sessions"][:5]
        self.save()

    def update_project_settings(self, project_path, settings: dict):
        proj = self.get_project_data(project_path)
        for k, v in settings.items():
            proj[k] = v
        self.save()

    def add_to_group(self, project_path, group_name, file_paths):
        proj = self.get_project_data(project_path)
        if group_name not in proj["groups"]:
            proj["groups"][group_name] = []
        for path in file_paths:
            if path not in proj["groups"][group_name]:
                proj["groups"][group_name].append(path)
        self.save()

    def remove_from_group(self, project_path, group_name, file_paths):
        proj = self.get_project_data(project_path)
        if group_name in proj["groups"]:
            for path in file_paths:
                if path in proj["groups"][group_name]:
                    proj["groups"][group_name].remove(path)
            self.save()
