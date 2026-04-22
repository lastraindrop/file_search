"""Shared web models and helpers for FileCortex routes."""

from __future__ import annotations

import os
import pathlib
import subprocess
import threading
from typing import Any, Literal

from pydantic import BaseModel, Field

from file_cortex_core import DataManager, FileUtils, FormatUtils, PathValidator, logger

ACTIVE_PROCESSES: dict[int, subprocess.Popen] = {}
PROCESS_LOCK = threading.Lock()


class ProjectOpenRequest(BaseModel):
    """Request model for opening a project."""

    path: str


class StageAllRequest(BaseModel):
    """Request model for staging all files in a project."""

    project_path: str
    mode: str = "files"
    apply_excludes: bool = True


class GenerateRequest(BaseModel):
    """Request model for generating file context."""

    files: list[str]
    project_path: str | None = None
    template_name: str | None = None
    export_format: str = "markdown"
    include_blueprint: bool = True


class FileRenameRequest(BaseModel):
    """Request model for renaming a file."""

    project_path: str
    path: str
    new_name: str


class FileDeleteRequest(BaseModel):
    """Request model for deleting files."""

    project_path: str
    paths: list[str]


class FileMoveRequest(BaseModel):
    """Request model for moving files."""

    src_paths: list[str]
    dst_dir: str


class FileSaveRequest(BaseModel):
    """Request model for saving file content."""

    path: str
    content: str = Field(..., max_length=10_000_000)


class FileCreateRequest(BaseModel):
    """Request model for creating a new file or directory."""

    parent_path: str
    name: str
    is_dir: bool = False


class FileArchiveRequest(BaseModel):
    """Request model for archiving files."""

    paths: list[str]
    output_name: str
    project_root: str


class OpenPathRequest(BaseModel):
    """Request model for opening a file or directory in the OS shell."""

    project_path: str
    path: str


class ChildrenRequest(BaseModel):
    """Request model for getting directory children."""

    path: str


class NoteRequest(BaseModel):
    """Request model for adding notes to files."""

    project_path: str
    file_path: str
    note: str


class TagRequest(BaseModel):
    """Request model for managing file tags."""

    project_path: str
    file_path: str
    tag: str
    action: Literal["add", "remove"]


class GlobalSettingsRequest(BaseModel):
    """Request model for updating global settings."""

    preview_limit_mb: float | None = None
    allowed_extensions: str | None = None
    token_threshold: int | None = None
    enable_noise_reducer: bool | None = None
    theme: str | None = None
    token_ratio: float | None = None
    settings: dict | None = None


class FavoriteRequest(BaseModel):
    """Request model for managing favorites."""

    project_path: str
    group_name: str
    file_paths: list[str]
    action: Literal["add", "remove"]


class SessionRequest(BaseModel):
    """Request model for saving sessions."""

    project_path: str
    data: dict


class ProjectSettingsRequest(BaseModel):
    """Request model for updating project settings."""

    project_path: str
    settings: dict


class ToolsUpdateRequest(BaseModel):
    """Request model for updating custom tools."""

    project_path: str
    tools: dict


class CategoriesUpdateRequest(BaseModel):
    """Request model for updating categories."""

    project_path: str
    categories: dict


class PathCollectionRequest(BaseModel):
    """Request model for collecting and formatting paths."""

    paths: list[str]
    project_root: str | None = None
    mode: str = "relative"
    separator: str = "\n"
    file_prefix: str = ""
    dir_suffix: str = ""


class WorkspacePinRequest(BaseModel):
    """Request model for pinning workspaces."""

    path: str


class CategorizeRequest(BaseModel):
    """Request model for categorizing files."""

    project_path: str
    paths: list[str]
    category_name: str


class StatsRequest(BaseModel):
    """Request model for getting file statistics."""

    paths: list[str]
    project_path: str | None = None


class ToolExecuteRequest(BaseModel):
    """Request model for executing tools."""

    project_path: str
    paths: list[str]
    tool_name: str


class BatchRenameRequest(BaseModel):
    """Request model for batch renaming files."""

    project_path: str
    paths: list[str]
    pattern: str
    replacement: str
    dry_run: bool = True


class ProcessTerminateRequest(BaseModel):
    """Request model for terminating processes."""

    pid: int


def get_dm() -> DataManager:
    """Returns a DataManager instance for the current context."""
    return DataManager()


def is_path_safe(target_path: str, project_root: str) -> bool:
    """Checks whether a target path stays within the registered project root."""
    return PathValidator.is_safe(target_path, project_root)


def get_valid_project_root(path_str: str) -> str | None:
    """Resolves the registered project root for a path."""
    return get_dm().resolve_project_root(path_str)


def get_project_config_for_path(path_str: str) -> tuple[str | None, dict | None]:
    """Returns the registered project root and its config for a path."""
    root = get_valid_project_root(path_str)
    if not root:
        return None, None
    return root, get_dm().get_project_data(root)


def _has_children(path_obj: pathlib.Path) -> bool:
    """Checks whether a directory has children."""
    try:
        with os.scandir(path_obj) as it:
            return any(it)
    except (PermissionError, OSError):
        return False


def get_node_info(path_obj: pathlib.Path, project_root: str) -> dict[str, Any]:
    """Returns normalized metadata for a file or directory node."""
    is_dir = path_obj.is_dir()
    meta = FileUtils.get_metadata(path_obj)
    _ = project_root
    return {
        "name": path_obj.name,
        "path": PathValidator.norm_path(path_obj),
        "type": "dir" if is_dir else "file",
        "has_children": is_dir and _has_children(path_obj),
        "mtime_fmt": FormatUtils.format_datetime(meta["mtime"]),
        "size_fmt": FormatUtils.format_size(meta["size"]),
        "size": meta["size"],
        "mtime": meta["mtime"],
        "ext": meta["ext"],
    }


def get_children(path_str: str) -> list[dict[str, Any]]:
    """Gets the children of a registered directory."""
    path = pathlib.Path(path_str)
    if not path.exists() or not path.is_dir():
        return []

    project_root, proj_config = get_project_config_for_path(path_str)
    if not project_root or proj_config is None:
        logger.warning(f"Blocking potentially unsafe path access: {path_str}")
        return []

    project_root_path = pathlib.Path(project_root)
    excludes = proj_config.get("excludes", "").split()
    git_spec = FileUtils.get_gitignore_spec(str(project_root_path))

    children = []
    try:
        with os.scandir(path) as it:
            entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
            norm_root = PathValidator.norm_path(project_root_path)
            for entry in entries:
                ep = pathlib.Path(entry.path)
                try:
                    rel = ep.resolve().relative_to(project_root_path.resolve())
                except ValueError:
                    norm_entry = PathValidator.norm_path(entry.path)
                    if norm_entry.startswith(norm_root.rstrip("/") + "/"):
                        rel = pathlib.Path(norm_entry[len(norm_root) :].lstrip("/"))
                    else:
                        continue

                if FileUtils.should_ignore(entry.name, rel, excludes, git_spec):
                    continue
                children.append(get_node_info(pathlib.Path(entry.path), project_root))
    except (PermissionError, OSError):
        logger.error(f"Permission denied for directory: {path_str}")
    except Exception as e:
        logger.error(f"Error listing children for {path_str}: {e}")
    return children
