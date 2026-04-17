#!/usr/bin/env python3
"""FileCortex Web Application.

A FastAPI-based web server providing file management, search,
and context generation APIs for the FileCortex application.
"""

import argparse
import asyncio
import json
import os
import pathlib
import signal
import subprocess
import threading
import uvicorn
from typing import Any

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from file_cortex_core import (
    ActionBridge,
    ContextFormatter,
    DataManager,
    FileOps,
    FileUtils,
    FormatUtils,
    PathValidator,
    logger,
    search_generator,
)

app = FastAPI(title="FileCortex v6.2.0 API")

ACTIVE_PROCESSES: dict[int, subprocess.Popen] = {}
PROCESS_LOCK = threading.Lock()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled server-side exceptions."""
    logger.error(f"Global Unhandled Exception: {exc}", exc_info=True)

    detail = f"Internal Server Error: {str(exc)}"
    if os.getenv("FCTX_PROD") == "1":
        detail = "Internal Server Error. Please check server logs for details."

    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": detail},
    )


def _get_dm() -> DataManager:
    """Returns a DataManager instance for the current context."""
    return DataManager()


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
    action: str


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
    action: str


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


def is_path_safe(target_path: str, project_root: str) -> bool:
    """Checks if a target path is safe within the project root.

    Args:
        target_path: The path to validate.
        project_root: The project root path.

    Returns:
        True if the path is safe, False otherwise.
    """
    return PathValidator.is_safe(target_path, project_root)


def get_valid_project_root(path_str: str) -> str | None:
    """Resolves the valid project root for a given path.

    Args:
        path_str: The path to resolve.

    Returns:
        The project root path or None if not found.
    """
    return _get_dm().resolve_project_root(path_str)


def get_project_config_for_path(
    path_str: str,
) -> tuple[str | None, dict | None]:
    """Retrieves project configuration for a path.

    Args:
        path_str: The path to look up.

    Returns:
        A tuple of (root, config) or (None, None).
    """
    root = get_valid_project_root(path_str)
    if not root:
        return None, None
    return root, _get_dm().get_project_data(root)


def _has_children(path_obj: pathlib.Path) -> bool:
    """Checks if a directory has any children.

    Args:
        path_obj: The directory path.

    Returns:
        True if the directory has children, False otherwise.
    """
    try:
        with os.scandir(path_obj) as it:
            return any(it)
    except (PermissionError, OSError):
        return False


def get_node_info(path_obj: pathlib.Path, project_root: str) -> dict[str, Any]:
    """Returns metadata for a file or directory node.

    Args:
        path_obj: The path to get info for.
        project_root: The project root for reference.

    Returns:
        A dictionary containing node metadata.
    """
    is_dir = path_obj.is_dir()
    meta = FileUtils.get_metadata(path_obj)
    mtime_fmt = FormatUtils.format_datetime(meta["mtime"])

    return {
        "name": path_obj.name,
        "path": PathValidator.norm_path(path_obj),
        "type": "dir" if is_dir else "file",
        "has_children": is_dir and _has_children(path_obj),
        "mtime_fmt": mtime_fmt,
        "size_fmt": FormatUtils.format_size(meta["size"]),
        "size": meta["size"],
        "mtime": meta["mtime"],
        "ext": meta["ext"],
    }


def get_children(path_str: str) -> list[dict[str, Any]]:
    """Gets the children of a directory.

    Args:
        path_str: The directory path.

    Returns:
        A list of child node dictionaries.
    """
    path = pathlib.Path(path_str)
    if not path.exists() or not path.is_dir():
        return []

    project_root, proj_config = get_project_config_for_path(path_str)
    if not project_root:
        logger.warning(f"Blocking potentially unsafe path access: {path_str}")
        return []

    project_root = pathlib.Path(project_root)
    excludes = proj_config.get("excludes", "").split()
    git_spec = FileUtils.get_gitignore_spec(str(project_root))

    children = []
    try:
        with os.scandir(path) as it:
            entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
            norm_root = PathValidator.norm_path(project_root)
            for entry in entries:
                ep = pathlib.Path(entry.path)
                try:
                    rel = ep.resolve().relative_to(pathlib.Path(project_root).resolve())
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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serves the main index page.

    Args:
        request: The incoming request.

    Returns:
        The rendered index.html template.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/open")
def open_project(req: ProjectOpenRequest) -> dict[str, Any]:
    """Opens and registers a project.

    Args:
        req: The project open request.

    Returns:
        The root node information.
    """
    try:
        p = PathValidator.validate_project(req.path)
        logger.info(f"AUDIT - Opening project: {p}")
        dm = _get_dm()

        dm.add_to_recent(str(p))
        dm.get_project_data(str(p))
        dm.save()

        root_node = get_node_info(p, p)
        return root_node
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/fs/children")
def api_children(req: ChildrenRequest) -> dict[str, Any]:
    """Gets directory children.

    Args:
        req: The children request.

    Returns:
        Directory children data.
    """
    p = pathlib.Path(req.path)
    children = get_children(req.path)
    return {
        "status": "ok",
        "parent": PathValidator.norm_path(p.parent) if p.parent else None,
        "children": children,
    }


@app.get("/api/content")
def get_content(path: str) -> dict[str, Any]:
    """Gets file content for preview.

    Args:
        path: The file path.

    Returns:
        File content and metadata.
    """
    p = pathlib.Path(path)

    if not get_valid_project_root(path):
        logger.warning(f"Blocking unauthorized content access: {path}")
        raise HTTPException(
            status_code=403,
            detail="Access denied (Path not within any project root)",
        )

    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if FileUtils.is_binary(p):
        return {"content": "--- Binary File (Preview Unavailable) ---"}
    try:
        dm = _get_dm()
        limit_mb = dm.data["global_settings"].get("preview_limit_mb", 1)
        max_preview = int(limit_mb * 1024 * 1024)
        content = FileUtils.read_text_smart(p, max_bytes=max_preview)

        return {
            "content": content,
            "encoding": "utf-8",
            "is_truncated": len(content.encode("utf-8", errors="ignore"))
            >= max_preview,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")


@app.post("/api/generate")
def generate_context(req: GenerateRequest) -> dict[str, Any]:
    """Generates formatted context for files.

    Args:
        req: The generate context request.

    Returns:
        Formatted content and token count.
    """
    root = None
    proj_config = None
    prompt_prefix = None

    if req.project_path:
        root, proj_config = get_project_config_for_path(req.project_path)
        final_root = root if root else req.project_path
        if proj_config and req.template_name:
            prompt_prefix = proj_config.get("prompt_templates", {}).get(
                req.template_name
            )
        if req.export_format == "xml":
            content = ContextFormatter.to_xml(
                req.files, root_dir=final_root, prompt_prefix=prompt_prefix
            )
        else:
            content = ContextFormatter.to_markdown(
                req.files, root_dir=final_root, prompt_prefix=prompt_prefix
            )
    else:
        if req.export_format == "xml":
            content = ContextFormatter.to_xml(req.files, prompt_prefix=None)
        else:
            content = ContextFormatter.to_markdown(req.files, prompt_prefix=None)

    tokens = FormatUtils.estimate_tokens(content)
    return {"content": content, "tokens": tokens}


@app.post("/api/fs/rename")
def rename_file(req: FileRenameRequest) -> dict[str, Any]:
    """Renames a file.

    Args:
        req: The rename request.

    Returns:
        The new path after renaming.
    """
    project_root = get_valid_project_root(req.project_path)
    if not project_root:
        raise HTTPException(
            status_code=403, detail="Access denied (Invalid project path)"
        )

    if not is_path_safe(req.path, project_root):
        raise HTTPException(status_code=403, detail="Access denied")

    if any(sep in req.new_name for sep in (os.sep, "/")):
        raise HTTPException(status_code=400, detail="Invalid characters in new name")

    try:
        logger.info(f"AUDIT - Renaming: {req.path} -> {req.new_name}")
        new_path = FileOps.rename_file(req.path, req.new_name)
        return {"status": "ok", "new_path": new_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/fs/batch_rename")
def api_batch_rename(req: BatchRenameRequest) -> dict[str, Any]:
    """Batch renames files.

    Args:
        req: The batch rename request.

    Returns:
        The rename results.
    """
    project_root = get_valid_project_root(req.project_path)
    if not project_root:
        raise HTTPException(status_code=403, detail="Access denied")

    for p in req.paths:
        if not is_path_safe(p, project_root):
            raise HTTPException(status_code=403, detail=f"Path unsafe: {p}")

    try:
        logger.info(
            f"AUDIT - Batch Renaming ({'Dry' if req.dry_run else 'Live'}): "
            f"{len(req.paths)} items"
        )
        results = FileOps.batch_rename(
            req.project_path,
            req.paths,
            req.pattern,
            req.replacement,
            req.dry_run,
        )
        return {"status": "ok", "results": results}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fs/delete")
def delete_files(req: FileDeleteRequest) -> dict[str, str]:
    """Deletes files.

    Args:
        req: The delete request.

    Returns:
        Status message.
    """
    project_root = get_valid_project_root(req.project_path)
    if not project_root:
        raise HTTPException(
            status_code=403, detail="Access denied (Invalid project path)"
        )

    try:
        for p in req.paths:
            if not is_path_safe(p, project_root):
                logger.warning(f"Blocking potentially unsafe delete access: {p}")
                raise HTTPException(status_code=403, detail=f"Access denied for {p}")
            logger.info(f"AUDIT - Deleting: {p}")
            FileOps.delete_file(p)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/fs/move")
def api_move(req: FileMoveRequest) -> dict[str, Any]:
    """Moves files to a destination directory.

    Args:
        req: The move request.

    Returns:
        Move results including moved and skipped paths.
    """
    try:
        moved_paths = []
        skipped_paths = []
        for src in req.src_paths:
            src_root = get_valid_project_root(src)
            dst_root = get_valid_project_root(req.dst_dir)

            if not src_root or not dst_root:
                logger.warning(
                    f"Blocking potentially unsafe move: {src} -> {req.dst_dir}"
                )
                skipped_paths.append(src)
                continue

            if PathValidator.norm_path(src_root) != PathValidator.norm_path(dst_root):
                logger.warning(
                    f"Blocking cross-project move: {src} ({src_root}) "
                    f"-> {req.dst_dir} ({dst_root})"
                )
                skipped_paths.append(src)
                continue

            logger.info(f"AUDIT - Moving: {src} -> {req.dst_dir}")
            new_path = FileOps.move_file(src, req.dst_dir)
            moved_paths.append(new_path)

        if skipped_paths and not moved_paths:
            raise HTTPException(
                status_code=403,
                detail=f"All moves blocked or cross-project: {skipped_paths}",
            )

        return {"status": "ok", "new_paths": moved_paths, "skipped": skipped_paths}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/fs/save")
def api_save(req: FileSaveRequest) -> dict[str, str]:
    """Saves content to a file.

    Args:
        req: The save request.

    Returns:
        Status message.
    """
    try:
        if not get_valid_project_root(req.path):
            raise HTTPException(status_code=403, detail="Access denied")

        logger.info(f"AUDIT - Saving content to: {req.path}")
        FileOps.save_content(req.path, req.content)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/fs/create")
def api_create(req: FileCreateRequest) -> dict[str, Any]:
    """Creates a new file or directory.

    Args:
        req: The create request.

    Returns:
        The path of the created item.
    """
    try:
        if not get_valid_project_root(req.parent_path):
            raise HTTPException(status_code=403, detail="Access denied")
        logger.info(
            f"AUDIT - Creating {'dir' if req.is_dir else 'file'}: "
            f"{req.name} in {req.parent_path}"
        )
        new_path = FileOps.create_item(req.parent_path, req.name, req.is_dir)
        return {"status": "ok", "path": new_path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/config/global")
def get_global_config() -> dict[str, Any]:
    """Gets global configuration.

    Returns:
        Global settings dictionary.
    """
    return _get_dm().data["global_settings"]


@app.post("/api/config/global")
def update_global_config(
    req: GlobalSettingsRequest,
) -> dict[str, Any]:
    """Updates global configuration.

    Args:
        req: The settings update request.

    Returns:
        Updated settings.
    """
    data = req.model_dump(exclude_unset=True)
    if "settings" in data and isinstance(data["settings"], dict):
        data.update(data.pop("settings"))

    _get_dm().update_global_settings(data)
    return {"status": "ok", "settings": _get_dm().data["global_settings"]}


@app.post("/api/fs/archive")
def api_archive(req: FileArchiveRequest) -> dict[str, str]:
    """Archives selected files.

    Args:
        req: The archive request.

    Returns:
        The archive path.
    """
    try:
        if not get_valid_project_root(req.project_root):
            raise HTTPException(status_code=403, detail="Access denied")

        for p in req.paths:
            if not is_path_safe(p, req.project_root):
                raise HTTPException(status_code=403, detail=f"Unsafe path: {p}")

        if any(sep in req.output_name for sep in (os.sep, "/")):
            raise HTTPException(
                status_code=400, detail="Invalid characters in output name"
            )

        logger.info(
            f"AUDIT - Archiving {len(req.paths)} items to {req.output_name} "
            f"in {req.project_root}"
        )
        output_file = os.path.join(req.project_root, req.output_name)
        result_path = FileOps.archive_selection(
            req.paths, output_file, req.project_root
        )
        return {"status": "ok", "archive_path": result_path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/project/config")
def get_proj_config(path: str) -> dict[str, Any]:
    """Gets project configuration.

    Args:
        path: A path within the project.

    Returns:
        Project configuration dictionary.
    """
    root, _ = get_project_config_for_path(path)
    if not root:
        raise HTTPException(status_code=403, detail="Access denied")
    return _get_dm().get_project_data(root)


@app.get("/api/project/prompt_templates")
def get_prompt_templates(path: str) -> dict[str, str]:
    """Gets project prompt templates.

    Args:
        path: A path within the project.

    Returns:
        Prompt templates dictionary.
    """
    root, proj_config = get_project_config_for_path(path)
    if not root or proj_config is None:
        return {}
    return proj_config.get("prompt_templates", {})


@app.get("/api/workspaces")
def get_workspaces() -> dict[str, Any]:
    """Gets all workspaces.

    Returns:
        Workspaces summary.
    """
    return _get_dm().get_workspaces_summary()


@app.post("/api/workspaces/pin")
def toggle_pin(req: WorkspacePinRequest) -> dict[str, bool]:
    """Toggles workspace pin status.

    Args:
        req: The pin request.

    Returns:
        The new pin status.
    """
    status = _get_dm().toggle_pinned(req.path)
    return {"is_pinned": status}


@app.get("/api/recent_projects")
def get_recent_projects_legacy() -> list[dict[str, str]]:
    """Gets recent projects (legacy endpoint).

    Returns:
        List of recent projects.
    """
    return [
        {"name": pathlib.Path(p).name, "path": p}
        for p in _get_dm().data["projects"].keys()
        if p and os.path.exists(p)
    ]


@app.post("/api/project/note")
def api_add_note(req: NoteRequest) -> dict[str, str]:
    """Adds a note to a file.

    Args:
        req: The note request.

    Returns:
        Status message.
    """
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    _get_dm().add_note(req.project_path, req.file_path, req.note)
    return {"status": "ok"}


@app.post("/api/project/tag")
def api_manage_tag(req: TagRequest) -> dict[str, str]:
    """Manages tags on a file.

    Args:
        req: The tag request.

    Returns:
        Status message.
    """
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    if req.action == "add":
        _get_dm().add_tag(req.project_path, req.file_path, req.tag)
    else:
        _get_dm().remove_tag(req.project_path, req.file_path, req.tag)
    return {"status": "ok"}


@app.post("/api/project/session")
def api_save_session(req: SessionRequest) -> dict[str, str]:
    """Saves a project session.

    Args:
        req: The session request.

    Returns:
        Status message.
    """
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    _get_dm().save_session(req.project_path, req.data)
    return {"status": "ok"}


@app.post("/api/project/favorites")
def api_manage_favorites(req: FavoriteRequest) -> dict[str, str]:
    """Manages favorite groups.

    Args:
        req: The favorites request.

    Returns:
        Status message.
    """
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    if req.action == "add":
        _get_dm().add_to_group(req.project_path, req.group_name, req.file_paths)
    else:
        _get_dm().remove_from_group(req.project_path, req.group_name, req.file_paths)
    return {"status": "ok"}


@app.post("/api/project/settings")
def update_settings(req: ProjectSettingsRequest) -> dict[str, str]:
    """Updates project settings.

    Args:
        req: The settings request.

    Returns:
        Status message.
    """
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    _get_dm().update_project_settings(req.project_path, req.settings)
    return {"status": "ok"}


@app.post("/api/project/tools")
def update_tools(req: ToolsUpdateRequest) -> dict[str, str]:
    """Updates custom tools configuration.

    Args:
        req: The tools update request.

    Returns:
        Status message.
    """
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        _get_dm().update_custom_tools(req.project_path, req.tools)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/project/stats")
def get_staging_stats(req: StatsRequest) -> dict[str, int]:
    """Gets file statistics.

    Args:
        req: The stats request.

    Returns:
        Total tokens and file count.
    """
    root = get_valid_project_root(req.project_path) if req.project_path else None

    manual_excludes = []
    use_git = True
    if root:
        proj_data = _get_dm().get_project_data(root)
        ex_str = proj_data.get("excludes", "")
        manual_excludes = [e.lower().strip() for e in ex_str.split() if e.strip()]

    all_files = FileUtils.flatten_paths(req.paths, root, manual_excludes, use_git)

    total_tokens = 0
    for f_str in all_files:
        p = pathlib.Path(f_str)
        if p.is_file() and p.exists() and not FileUtils.is_binary(p):
            try:
                content = FileUtils.read_text_smart(p)
                total_tokens += FormatUtils.estimate_tokens(content)
            except Exception as e:
                logger.debug(f"Stats calculation failed for {f_str}: {e}")

    return {"total_tokens": total_tokens, "file_count": len(all_files)}


@app.post("/api/project/categories")
def update_categories(req: CategoriesUpdateRequest) -> dict[str, str]:
    """Updates quick categories.

    Args:
        req: The categories update request.

    Returns:
        Status message.
    """
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        _get_dm().update_quick_categories(req.project_path, req.categories)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/global/settings")
def get_global_settings() -> dict[str, Any]:
    """Gets global settings.

    Returns:
        Global settings dictionary.
    """
    return _get_dm().data.get("global_settings", {})


@app.post("/api/global/settings")
def update_global_settings(req: GlobalSettingsRequest) -> dict[str, str]:
    """Updates global settings.

    Args:
        req: The settings request.

    Returns:
        Status message.
    """
    data = req.model_dump(exclude_unset=True)
    if "settings" in data and isinstance(data["settings"], dict):
        legacy_data = data.pop("settings")
        data.update(legacy_data)

    _get_dm().update_global_settings(data)
    return {"status": "ok"}


@app.post("/api/actions/stage_all")
def api_stage_all(req: StageAllRequest) -> dict[str, Any]:
    """Stages all files in a project.

    Args:
        req: The stage all request.

    Returns:
        Number of files staged.
    """
    root, proj_config = get_project_config_for_path(req.project_path)
    if not root:
        raise HTTPException(status_code=403, detail="Project not registered")

    manual_excludes = (
        proj_config.get("excludes", "").split() if req.apply_excludes else []
    )

    try:
        items = FileUtils.get_project_items(
            root, manual_excludes, use_gitignore=True, mode=req.mode
        )
        added = _get_dm().batch_stage(root, items)
        return {"status": "ok", "added_count": added}
    except Exception as e:
        logger.error(f"Stage All failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/actions/categorize")
def api_categorize(req: CategorizeRequest) -> dict[str, Any]:
    """Categorizes files into a directory.

    Args:
        req: The categorize request.

    Returns:
        Categorize results.
    """
    try:
        if not get_valid_project_root(req.project_path):
            raise HTTPException(status_code=403, detail="Access denied")

        logger.info(
            f"AUDIT - Batch categorizing {len(req.paths)} items "
            f"to '{req.category_name}'"
        )
        moved = FileOps.batch_categorize(req.project_path, req.paths, req.category_name)
        return {"status": "ok", "moved_count": len(moved), "paths": moved}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/actions/execute")
def api_execute_tool(req: ToolExecuteRequest) -> dict[str, Any]:
    """Executes a custom tool on files.

    Args:
        req: The tool execution request.

    Returns:
        Tool execution results.
    """
    try:
        project_root = get_valid_project_root(req.project_path)
        if not project_root:
            raise HTTPException(status_code=403, detail="Access denied")

        proj_config = _get_dm().get_project_data(req.project_path)
        template = proj_config.get("custom_tools", {}).get(req.tool_name)
        if not template:
            raise HTTPException(status_code=404, detail="Tool template not found")

        results = []
        for p in req.paths:
            if not is_path_safe(p, project_root):
                continue

            try:
                proc = ActionBridge.create_process(template, p, project_root)
                with PROCESS_LOCK:
                    ACTIVE_PROCESSES[proc.pid] = proc

                try:
                    exec_timeout = int(os.getenv("FCTX_EXEC_TIMEOUT", "300"))
                    stdout, stderr = proc.communicate(timeout=exec_timeout)

                    results.append(
                        {
                            "path": p,
                            "stdout": stdout,
                            "stderr": stderr,
                            "exit_code": proc.returncode,
                            "pid": proc.pid,
                        }
                    )
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                        )
                    else:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    stdout, stderr = proc.communicate()
                    results.append(
                        {
                            "path": p,
                            "error": f"Command timed out after {exec_timeout} seconds",
                        }
                    )
                except Exception as e:
                    proc.kill()
                    results.append({"path": p, "error": f"Process error: {e}"})
                finally:
                    with PROCESS_LOCK:
                        ACTIVE_PROCESSES.pop(proc.pid, None)
            except Exception as e:
                results.append({"path": p, "error": f"Execution failed to start: {e}"})

        return {"status": "ok", "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/fs/collect_paths")
def collect_paths_api(req: PathCollectionRequest) -> dict[str, str]:
    """Collects and formats paths.

    Args:
        req: The path collection request.

    Returns:
        Formatted paths string.
    """
    try:
        if req.project_root:
            if not get_valid_project_root(req.project_root):
                raise HTTPException(status_code=403, detail="Unauthorized project root")

        res = FormatUtils.collect_paths(
            req.paths,
            req.project_root,
            req.mode,
            req.separator,
            req.file_prefix,
            req.dir_suffix,
        )
        return {"result": res}
    except Exception as e:
        logger.error(f"Path collection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/actions/terminate")
def api_terminate_process(req: ProcessTerminateRequest) -> dict[str, Any]:
    """Terminates a running process.

    Args:
        req: The terminate request.

    Returns:
        Termination status.
    """
    with PROCESS_LOCK:
        proc = ACTIVE_PROCESSES.get(req.pid)
        if proc:
            logger.info(f"AUDIT - Terminating process {req.pid}")
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(req.pid)],
                        capture_output=True,
                    )
                else:
                    os.killpg(os.getpgid(req.pid), signal.SIGTERM)
                return {"status": "ok"}
            except Exception as e:
                try:
                    os.kill(req.pid, signal.SIGTERM)
                    return {"status": "ok", "msg": f"killpg failed: {e}"}
                except Exception:
                    pass
                return {"status": "error", "msg": str(e)}
        else:
            return {
                "status": "error",
                "msg": "Process not found or already finished",
            }


@app.websocket("/ws/search")
async def websocket_search(
    websocket: WebSocket,
    path: str,
    query: str,
    mode: str = "smart",
    inverse: bool = False,
    case_sensitive: bool = False,
) -> None:
    """WebSocket endpoint for real-time search.

    Args:
        websocket: The WebSocket connection.
        path: Project path.
        query: Search query.
        mode: Search mode.
        inverse: Inverse search flag.
        case_sensitive: Case sensitivity flag.
    """
    await websocket.accept()

    project_root, proj_config = get_project_config_for_path(path)

    if not project_root:
        logger.warning(f"Blocking potentially unsafe search access: {path}")
        await websocket.send_json(
            {"status": "ERROR", "msg": "Access denied (Path unsafe)"}
        )
        await websocket.close()
        return

    p = pathlib.Path(path)
    excludes = proj_config.get("excludes", "")

    result_queue: asyncio.Queue = asyncio.Queue()
    main_loop = asyncio.get_running_loop()
    stop_event = threading.Event()

    def run_search() -> None:
        try:
            max_size = proj_config.get("max_search_size_mb", 5)
            for res_dict in search_generator(
                p,
                query,
                mode,
                excludes,
                include_dirs=False,
                is_inverse=inverse,
                case_sensitive=case_sensitive,
                max_size_mb=max_size,
                stop_event=stop_event,
            ):
                if stop_event.is_set():
                    break
                main_loop.call_soon_threadsafe(
                    result_queue.put_nowait,
                    {
                        "name": os.path.basename(res_dict["path"]),
                        "path": res_dict["path"],
                        "type": res_dict["match_type"],
                        "size": res_dict["size"],
                        "size_fmt": FormatUtils.format_size(res_dict["size"]),
                        "mtime": res_dict["mtime"],
                        "mtime_fmt": res_dict.get("mtime_fmt", ""),
                        "ext": res_dict["ext"],
                    },
                )
        finally:
            main_loop.call_soon_threadsafe(result_queue.put_nowait, "DONE")

    search_task = asyncio.create_task(asyncio.to_thread(run_search))

    try:
        while True:
            res = await result_queue.get()
            if res == "DONE":
                await websocket.send_json({"status": "DONE"})
                break
            await websocket.send_json(res)
    except WebSocketDisconnect:
        logger.info("Search client disconnected")
        stop_event.set()
        search_task.cancel()
    except Exception as e:
        logger.error(f"Search error: {e}")
        search_task.cancel()
        try:
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
        except Exception:
            pass


@app.websocket("/ws/actions/execute")
async def websocket_action_stream(
    websocket: WebSocket,
    project_path: str,
    tool_name: str,
    path: str,
) -> None:
    """WebSocket endpoint for streaming tool execution.

    Args:
        websocket: The WebSocket connection.
        project_path: Project path.
        tool_name: Tool name to execute.
        path: File path to process.
    """
    await websocket.accept()

    project_root = get_valid_project_root(project_path)
    if not project_root:
        await websocket.send_json({"status": "ERROR", "msg": "Access denied"})
        await websocket.close()
        return

    proj_config = _get_dm().get_project_data(project_path)
    template = proj_config["custom_tools"].get(tool_name)
    if not template:
        await websocket.send_json({"status": "ERROR", "msg": "Tool template not found"})
        await websocket.close()
        return

    if not is_path_safe(path, project_root):
        await websocket.send_json({"status": "ERROR", "msg": "Path unsafe"})
        await websocket.close()
        return

    current_pid = [None]
    result_queue: asyncio.Queue = asyncio.Queue()
    main_loop = asyncio.get_running_loop()

    def run_stream() -> None:
        proc = None
        try:
            proc = ActionBridge.create_process(template, path, project_root)
            current_pid[0] = proc.pid
            with PROCESS_LOCK:
                ACTIVE_PROCESSES[proc.pid] = proc

            main_loop.call_soon_threadsafe(result_queue.put_nowait, {"pid": proc.pid})

            for line in proc.stdout:
                main_loop.call_soon_threadsafe(result_queue.put_nowait, {"out": line})

            proc.wait()
            with PROCESS_LOCK:
                ACTIVE_PROCESSES.pop(proc.pid, None)
            main_loop.call_soon_threadsafe(
                result_queue.put_nowait, {"exit_code": proc.returncode}
            )
        except Exception as e:
            main_loop.call_soon_threadsafe(result_queue.put_nowait, {"error": str(e)})
        finally:
            if proc and proc.pid:
                with PROCESS_LOCK:
                    ACTIVE_PROCESSES.pop(proc.pid, None)
            main_loop.call_soon_threadsafe(result_queue.put_nowait, "DONE")

    stream_task = asyncio.create_task(asyncio.to_thread(run_stream))

    try:
        while True:
            res = await result_queue.get()
            if res == "DONE":
                await websocket.send_json({"status": "DONE"})
                break
            await websocket.send_json(res)
    except WebSocketDisconnect:
        if current_pid[0]:
            pid = current_pid[0]
            logger.info(
                f"AUDIT - Terminating abandoned process {pid} "
                "due to WebSocket disconnect"
            )
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                    )
                else:
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                    except Exception:
                        os.kill(pid, signal.SIGTERM)

                with PROCESS_LOCK:
                    ACTIVE_PROCESSES.pop(pid, None)
            except Exception as e:
                logger.error(f"Cleanup failed for pid {pid}: {e}")
    except Exception as e:
        logger.error(f"Action stream error: {e}")
        try:
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
        except Exception:
            pass
    finally:
        stream_task.cancel()


def main() -> None:
    """Entry point for the web server."""
    parser = argparse.ArgumentParser(description="FileCortex Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "web_app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
