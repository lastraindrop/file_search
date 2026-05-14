"""Project management routes — workspace CRUD, settings, favorites."""

from __future__ import annotations

import os
import pathlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from file_cortex_core import DataManager, PathValidator, logger
from routers.schemas import (
    CategoriesUpdateRequest,
    FavoriteRequest,
    NoteRequest,
    ProjectOpenRequest,
    ProjectSettingsRequest,
    SessionRequest,
    TagRequest,
    ToolsUpdateRequest,
    WorkspacePinRequest,
)
from routers.services import (
    get_dm,
    get_node_info,
    get_project_config_for_path,
    get_valid_project_root,
    is_path_safe,
)

project_router = APIRouter()
_dm_dep = Depends(get_dm)


@project_router.post("/api/open")
def open_project(
    req: ProjectOpenRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Opens and registers a project."""
    try:
        p = PathValidator.validate_project(req.path)
        logger.info(f"AUDIT - Opening project: {p}")

        dm.add_to_recent(str(p))
        dm.get_project_data(str(p))
        dm.save()

        return get_node_info(p, str(p))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@project_router.get("/api/project/config")
def get_proj_config(path: str, dm: DataManager = _dm_dep) -> dict[str, Any]:
    """Gets project configuration."""
    root, _ = get_project_config_for_path(path, dm)
    if not root:
        raise HTTPException(status_code=403, detail="Access denied")
    return dm.get_project_data(root)


@project_router.get("/api/project/prompt_templates")
def get_prompt_templates(path: str, dm: DataManager = _dm_dep) -> dict[str, str]:
    """Gets project prompt templates."""
    root, proj_config = get_project_config_for_path(path, dm)
    if not root or proj_config is None:
        return {}
    return proj_config.get("prompt_templates", {})


@project_router.get("/api/workspaces")
def get_workspaces(dm: DataManager = _dm_dep) -> dict[str, Any]:
    """Gets all workspaces."""
    return dm.get_workspaces_summary()


@project_router.post("/api/workspaces/pin")
def toggle_pin(
    req: WorkspacePinRequest, dm: DataManager = _dm_dep
) -> dict[str, bool]:
    """Toggles workspace pin status."""
    return {"is_pinned": dm.toggle_pinned(req.path)}


@project_router.get("/api/recent_projects")
def get_recent_projects_legacy(dm: DataManager = _dm_dep) -> list[dict[str, str]]:
    """Gets recent projects using the legacy response shape."""
    return [
        {"name": pathlib.Path(p).name, "path": p}
        for p in dm.config.projects
        if p and os.path.exists(p)
    ]


@project_router.post("/api/project/note")
def api_add_note(req: NoteRequest, dm: DataManager = _dm_dep) -> dict[str, str]:
    """Adds a note to a file."""
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    dm.add_note(req.project_path, req.file_path, req.note)
    return {"status": "ok"}


@project_router.post("/api/project/tag")
def api_manage_tag(req: TagRequest, dm: DataManager = _dm_dep) -> dict[str, str]:
    """Manages tags on a file."""
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    if req.action == "add":
        dm.add_tag(req.project_path, req.file_path, req.tag)
    else:
        dm.remove_tag(req.project_path, req.file_path, req.tag)
    return {"status": "ok"}


@project_router.post("/api/project/session")
def api_save_session(
    req: SessionRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Saves a project session."""
    if not get_valid_project_root(req.project_path, dm):
        raise HTTPException(status_code=403, detail="Access denied")
    dm.save_session(req.project_path, req.data)
    return {"status": "ok"}


@project_router.post("/api/project/favorites")
def api_manage_favorites(
    req: FavoriteRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Manages favorite groups."""
    if not get_valid_project_root(req.project_path, dm):
        raise HTTPException(status_code=403, detail="Access denied")
    for file_path in req.file_paths:
        if not is_path_safe(file_path, req.project_path):
            raise HTTPException(status_code=403, detail=f"Path unsafe: {file_path}")
    if req.action == "add":
        dm.add_to_group(req.project_path, req.group_name, req.file_paths)
    else:
        dm.remove_from_group(req.project_path, req.group_name, req.file_paths)
    return {"status": "ok"}


@project_router.post("/api/project/settings")
def update_settings(
    req: ProjectSettingsRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Updates project settings."""
    if not get_valid_project_root(req.project_path, dm):
        raise HTTPException(status_code=403, detail="Access denied")
    dm.update_project_settings(req.project_path, req.settings)
    return {"status": "ok"}


@project_router.post("/api/project/tools")
def update_tools(
    req: ToolsUpdateRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Updates custom tools configuration."""
    if not get_valid_project_root(req.project_path, dm):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        dm.update_custom_tools(req.project_path, req.tools)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@project_router.post("/api/project/categories")
def update_categories(
    req: CategoriesUpdateRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Updates quick categories."""
    if not get_valid_project_root(req.project_path, dm):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        dm.update_quick_categories(req.project_path, req.categories)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
