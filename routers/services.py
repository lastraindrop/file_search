"""Service layer and helper functions for FileCortex routes."""

from __future__ import annotations

import os
import pathlib
from typing import Any

from file_cortex_core import DataManager, FileUtils, FormatUtils, PathValidator, logger


def get_dm() -> DataManager:
    """Returns a DataManager instance for the current context.

    Used as a FastAPI dependency.
    """
    return DataManager()


def is_path_safe(target_path: str, project_root: str) -> bool:
    """Checks whether a target path stays within the registered project root."""
    return PathValidator.is_safe(target_path, project_root)


def get_valid_project_root(path_str: str, dm: DataManager | None = None) -> str | None:
    """Resolves the registered project root for a path."""
    dm = dm or get_dm()
    return dm.resolve_project_root(path_str)


def get_project_config_for_path(
    path_str: str, dm: DataManager | None = None
) -> tuple[str | None, dict | None]:
    """Returns the registered project root and its config for a path."""
    root = get_valid_project_root(path_str, dm)
    if not root:
        return None, None
    dm = dm or get_dm()
    return root, dm.get_project_data(root)


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


def get_children(path_str: str, dm: DataManager | None = None) -> list[dict[str, Any]]:
    """Gets the children of a registered directory."""
    path = pathlib.Path(path_str)
    if not path.exists() or not path.is_dir():
        return []

    root_dm = dm or get_dm()
    project_root, proj_config = get_project_config_for_path(path_str, root_dm)
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
