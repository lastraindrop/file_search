#!/usr/bin/env python3
"""Configuration management module for FileCortex.

Manages application and project configuration with atomic persistence.
"""

import copy
import json
import logging
import logging.handlers
import os
import pathlib
import tempfile
import threading
import time
from typing import Any, Final

from pydantic import BaseModel, Field

from .security import PathValidator

# Application constants
APP_NAME: Final = "FileCortex"
MAX_LOG_SIZE: Final = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT: Final = 5


class SearchSettings(BaseModel):
    """Configuration for search operations."""
    mode: str = "smart"
    case_sensitive: bool = False
    inverse: bool = False
    include_dirs: bool = False


class CollectionProfile(BaseModel):
    """Formatting profile for path collection."""
    prefix: str = ""
    suffix: str = ""
    sep: str = "\\n"


class ProjectConfig(BaseModel):
    """Schema for individual project configuration."""
    excludes: str = (
        ".git .idea __pycache__ venv node_modules .vscode dist build "
        ".DS_Store *.pyc *.png *.jpg *.exe *.dll *.so *.dylib .env .cache"
    )
    max_search_size_mb: int = 10
    staging_list: list[str] = Field(default_factory=list)
    current_group: str = "Default"
    groups: dict[str, list[str]] = Field(default_factory=lambda: {"Default": []})
    notes: dict[str, str] = Field(default_factory=dict)
    tags: dict[str, list[str]] = Field(default_factory=dict)
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    custom_tools: dict[str, str] = Field(
        default_factory=lambda: {
            "Summary": 'python -c "import sys; print(f\'Summary for {sys.argv[1]}\')" {path}',
            "Lint": "python -m py_compile {path}",
        }
    )
    quick_categories: dict[str, str] = Field(
        default_factory=lambda: {"Scripts": "scripts", "Docs": "docs"}
    )
    prompt_templates: dict[str, str] = Field(
        default_factory=lambda: {
            "Code Review": (
                "Please review the following code for logic errors, "
                "potential bugs, and code style. Focus on security and performance. {files}"
            ),
            "Summary": (
                "Please provide a concise summary of the functionality "
                "and purpose of each of the following files. {files}"
            ),
            "Docstring": (
                "Generate professional docstrings for all functions "
                "and classes in these files. {files}"
            ),
        }
    )
    search_settings: SearchSettings = Field(default_factory=SearchSettings)
    collection_profiles: dict[str, CollectionProfile] = Field(
        default_factory=lambda: {
            "Default (@, /)": CollectionProfile(prefix="@", suffix="/", sep="\\n"),
            "RAG Style": CollectionProfile(prefix="file:", suffix="[dir]", sep=" "),
            "Simple List": CollectionProfile(prefix="", suffix="", sep="\\n"),
        }
    )
    token_threshold: int = 100000


class GlobalSettings(BaseModel):
    """Global application-wide settings."""
    preview_limit_mb: float = 1.0
    token_threshold: int = 128000
    enable_noise_reducer: bool = False
    token_ratio: float = 4.0
    theme: str = "dark"


class AppConfig(BaseModel):
    """Root configuration schema for FileCortex."""
    last_directory: str = ""
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    recent_projects: list[str] = Field(default_factory=list)
    pinned_projects: list[str] = Field(default_factory=list)
    global_settings: GlobalSettings = Field(default_factory=GlobalSettings)


def _setup_logging() -> logging.Logger:
    """Setup logging with rotation."""
    logger = logging.getLogger("FileCortex")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    log_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    log_dir = pathlib.Path.home() / ".filecortex" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "filecortex.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    except OSError:
        pass

    logger.info("FileCortex logger initialized")
    return logger


logger = _setup_logging()

_CONFIG_FILE: pathlib.Path | None = None


def get_app_dir() -> pathlib.Path:
    """Returns the application data directory, creating it if necessary."""
    home = pathlib.Path.home()
    app_dir = home / ".filecortex"
    try:
        app_dir.mkdir(exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create app directory: {e}")
    return app_dir


def _get_config_file() -> pathlib.Path:
    """Returns the configuration file path (singleton)."""
    global _CONFIG_FILE
    if _CONFIG_FILE is None:
        _CONFIG_FILE = get_app_dir() / "config.json"
    return _CONFIG_FILE


class DataManager:
    """Manages application and project configuration with thread-safe access.

    This class acts as the Single Source of Truth (SSOT) for all settings,
    utilizing Pydantic models for strict validation and atomic file writes
    for persistence.
    """

    _instance: "DataManager | None" = None
    _lock = threading.RLock()

    MUTABLE_SETTINGS: Final = frozenset(
        {
            "excludes",
            "max_search_size_mb",
            "staging_list",
            "current_group",
            "prompt_templates",
            "search_settings",
        }
    )

    def __new__(cls) -> "DataManager":
        """Creates or returns the singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_data()
            return cls._instance

    def __init__(self) -> None:
        """Initializer (logic handled in __new__ and _init_data)."""

    def _init_data(self) -> None:
        """Initializes the internal config state."""
        self.config: AppConfig = AppConfig()
        self.load()

    @property
    def data(self) -> dict[str, Any]:
        """Provides a dictionary view of the config for legacy compatibility.

        DEPRECATED: Use direct access to self.config where possible.
        """
        return self.config.model_dump()

    def load(self) -> None:
        """Loads configuration from disk with validation and normalization.

        Ensures all keys are properly normalized according to the current
        platform's rules. Legacy keys are migrated on-the-fly.
        """
        with self._lock:
            config_file = _get_config_file()
            if not config_file.exists():
                return

            try:
                with open(config_file, encoding="utf-8") as f:
                    raw_data = json.load(f)

                # Migrate and normalize project keys
                if "projects" in raw_data:
                    normalized_projects = {}
                    for k, v in raw_data["projects"].items():
                        try:
                            norm_k = PathValidator.norm_path(k)
                            if norm_k:
                                normalized_projects[norm_k] = v
                        except Exception as e:
                            logger.error(f"Failed to normalize project key '{k}': {e}")
                    raw_data["projects"] = normalized_projects

                # Validate against schema
                self.config = AppConfig.model_validate(raw_data)

                # Ensure list normalization
                self.config.recent_projects = [
                    p for p in [PathValidator.norm_path(x) for x in self.config.recent_projects] if p
                ]
                self.config.pinned_projects = [
                    p for p in [PathValidator.norm_path(x) for x in self.config.pinned_projects] if p
                ]

            except Exception as e:
                logger.error(f"Failed to load or validate configuration: {e}")

    def save(self) -> None:
        """Atomically persists the current configuration to disk."""
        with self._lock:
            config_file = _get_config_file()
            temp_path: str | None = None
            try:
                # model_dump_json ensures we have a valid serialization
                data_json = self.config.model_dump_json(indent=4)

                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    suffix=".json.tmp",
                    dir=str(config_file.parent),
                    delete=False,
                ) as f:
                    temp_path = f.name
                    f.write(data_json)

                # Atomic replacement with retries for Windows locking issues
                for attempt in range(BACKUP_COUNT):
                    try:
                        os.replace(temp_path, config_file)
                        temp_path = None
                        break
                    except PermissionError:
                        if attempt == BACKUP_COUNT - 1:
                            raise
                        time.sleep(0.05 * (attempt + 1))

            except Exception as e:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                logger.error(f"Failed to save configuration: {e}")
                raise e

    def add_to_recent(self, path: str) -> None:
        """Adds a project path to the recent list, maintaining a cap.

        Args:
            path: The project root directory path.
        """
        with self._lock:
            norm_p = PathValidator.norm_path(path)
            if not norm_p:
                return

            if norm_p in self.config.recent_projects:
                self.config.recent_projects.remove(norm_p)

            self.config.recent_projects.insert(0, norm_p)
            self.config.recent_projects = self.config.recent_projects[:15]
            self.config.last_directory = norm_p
            self.save()

    def toggle_pinned(self, path: str) -> bool:
        """Toggles the pinned status of a workspace.

        Args:
            path: The project path to toggle.

        Returns:
            The new pinned status (True if pinned).
        """
        with self._lock:
            norm_p = PathValidator.norm_path(path)
            if not norm_p:
                return False

            if norm_p in self.config.pinned_projects:
                self.config.pinned_projects.remove(norm_p)
                status = False
            else:
                self.config.pinned_projects.append(norm_p)
                status = True
            self.save()
            return status

    def get_workspaces_summary(self) -> dict[str, list[dict[str, str]]]:
        """Returns a summarized view of pinned and recent workspaces."""
        with self._lock:
            return {
                "pinned": [
                    {"path": p, "name": pathlib.Path(p).name}
                    for p in self.config.pinned_projects
                    if os.path.exists(p)
                ],
                "recent": [
                    {"path": p, "name": pathlib.Path(p).name}
                    for p in self.config.recent_projects
                    if os.path.exists(p) and p not in self.config.pinned_projects
                ],
            }

    def get_project_data_obj(self, path_str: str) -> ProjectConfig:
        """Retrieves the ProjectConfig object for a path, creating if needed.

        Args:
            path_str: The project root path.

        Returns:
            The ProjectConfig instance.
        """
        with self._lock:
            norm_p = PathValidator.norm_path(path_str)
            if norm_p not in self.config.projects:
                self.config.projects[norm_p] = ProjectConfig()
            return self.config.projects[norm_p]

    def get_project_data(self, path_str: str) -> dict[str, Any]:
        """Legacy compatibility wrapper for get_project_data_obj."""
        return self.get_project_data_obj(path_str).model_dump()

    def batch_stage(self, project_path: str, paths: list[str]) -> int:
        """Adds multiple paths to a project's staging list.

        Args:
            project_path: The root path of the project.
            paths: List of file paths to stage.

        Returns:
            The number of new items actually added.
        """
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            added_count = 0
            for raw_p in paths:
                p = PathValidator.norm_path(raw_p)
                if p and p not in proj.staging_list:
                    proj.staging_list.append(p)
                    added_count += 1
            if added_count > 0:
                self.save()
            return added_count

    def resolve_project_root(self, target_path_str: str) -> str | None:
        """Identifies which registered project a path belongs to.

        Args:
            target_path_str: The path to check.

        Returns:
            The normalized project root path, or None if not found.
        """
        try:
            target = PathValidator.norm_path(target_path_str)
            if not target:
                return None
            # Search from longest root to shortest to handle nested projects correctly
            for p_root in sorted(self.config.projects.keys(), key=len, reverse=True):
                if target == p_root or target.startswith(p_root.rstrip("/") + "/"):
                    return p_root
        except (ValueError, OSError):
            pass
        return None

    def add_note(self, project_path: str, file_path: str, note: str) -> None:
        """Stores a note for a specific file."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            norm_f = PathValidator.norm_path(file_path)
            if norm_f:
                proj.notes[norm_f] = note
                self.save()

    def add_tag(self, project_path: str, file_path: str, tag: str) -> None:
        """Adds a tag to a file."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            norm_f = PathValidator.norm_path(file_path)
            if norm_f:
                if norm_f not in proj.tags:
                    proj.tags[norm_f] = []
                if tag not in proj.tags[norm_f]:
                    proj.tags[norm_f].append(tag)
                    self.save()

    def remove_tag(self, project_path: str, file_path: str, tag: str) -> None:
        """Removes a tag from a file."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            norm_f = PathValidator.norm_path(file_path)
            if norm_f in proj.tags and tag in proj.tags[norm_f]:
                proj.tags[norm_f].remove(tag)
                self.save()

    def save_session(self, project_path: str, session_data: dict) -> None:
        """Records a user session for a project."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            proj.sessions.insert(0, session_data)
            proj.sessions = proj.sessions[:5]
            self.save()

    def update_project_settings(self, project_path: str, settings: dict) -> None:
        """Updates multiple project settings, enforcing whitelists.

        Args:
            project_path: The project root.
            settings: Dictionary of keys and values to update.
        """
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            for k, v in settings.items():
                if k in self.MUTABLE_SETTINGS:
                    if k == "staging_list" and isinstance(v, list):
                        proj.staging_list = [
                            p for p in [PathValidator.norm_path(x) for x in v] if p
                        ]
                    elif k == "search_settings" and isinstance(v, dict):
                        proj.search_settings = SearchSettings.model_validate(v)
                    else:
                        setattr(proj, k, v)
                else:
                    logger.warning(f"Blocked attempt to modify protected project key: {k}")
            self.save()

    def update_custom_tools(self, project_path: str, tools: dict[str, str]) -> None:
        """Updates the custom tools dictionary for a project."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            proj.custom_tools = tools
            self.save()

    def update_quick_categories(self, project_path: str, categories: dict[str, str]) -> None:
        """Updates quick categories, ensuring no traversal in relative paths."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            for name, rel_dir in categories.items():
                if ".." in rel_dir:
                    raise ValueError(f"Category path '{rel_dir}' contains illegal '..' traversal.")
            proj.quick_categories = categories
            self.save()

    def add_to_group(self, project_path: str, group_name: str, file_paths: list[str]) -> None:
        """Adds files to a favorite group."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            if group_name not in proj.groups:
                proj.groups[group_name] = []
            for raw_p in file_paths:
                p = PathValidator.norm_path(raw_p)
                if p and p not in proj.groups[group_name]:
                    proj.groups[group_name].append(p)
            self.save()

    def remove_from_group(self, project_path: str, group_name: str, file_paths: list[str]) -> None:
        """Removes files from a favorite group."""
        with self._lock:
            proj = self.get_project_data_obj(project_path)
            if group_name in proj.groups:
                for raw_path in file_paths:
                    norm_p = PathValidator.norm_path(raw_path)
                    if norm_p in proj.groups[group_name]:
                        proj.groups[group_name].remove(norm_p)
                self.save()

    def update_global_settings(self, settings: dict) -> None:
        """Updates global settings with validation."""
        with self._lock:
            current = self.config.global_settings.model_dump()
            current.update(settings)
            self.config.global_settings = GlobalSettings.model_validate(current)
            self.save()
