"""File system routes — CRUD operations on files and directories."""

from __future__ import annotations

import os
import pathlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from file_cortex_core import (
    DataManager,
    FileOps,
    FileUtils,
    FormatUtils,
    PathValidator,
    logger,
)
from routers.schemas import (
    BatchRenameRequest,
    ChildrenRequest,
    FileArchiveRequest,
    FileCreateRequest,
    FileDeleteRequest,
    FileMoveRequest,
    FileRenameRequest,
    FileSaveRequest,
    OpenPathRequest,
    PathCollectionRequest,
)
from routers.services import (
    get_children,
    get_dm,
    get_valid_project_root,
    is_path_safe,
)

fs_router = APIRouter()
_dm_dep = Depends(get_dm)


@fs_router.post("/api/fs/children")
def api_children(
    req: ChildrenRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Gets directory children."""
    p = pathlib.Path(req.path)
    if not get_valid_project_root(req.path, dm):
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "status": "ok",
        "parent": PathValidator.norm_path(p.parent) if p.parent else None,
        "children": get_children(req.path, dm),
    }


@fs_router.get("/api/content")
def get_content(path: str, dm: DataManager = _dm_dep) -> dict[str, Any]:
    """Gets file content for preview."""
    p = pathlib.Path(path)

    if not get_valid_project_root(path, dm):
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
        limit_mb = dm.config.global_settings.preview_limit_mb
        max_preview = int(round(limit_mb * 1024 * 1024))
        content = FileUtils.read_text_smart(p, max_bytes=max_preview)

        return {
            "content": content,
            "encoding": "utf-8",
            "is_truncated": len(content.encode("utf-8", errors="ignore"))
            >= max_preview,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}") from e


@fs_router.post("/api/fs/rename")
def rename_file(
    req: FileRenameRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Renames a file."""
    project_root = get_valid_project_root(req.project_path, dm)
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@fs_router.post("/api/fs/batch_rename")
def api_batch_rename(
    req: BatchRenameRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Batch renames files."""
    project_root = get_valid_project_root(req.project_path, dm)
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@fs_router.post("/api/fs/delete")
def delete_files(req: FileDeleteRequest, dm: DataManager = _dm_dep) -> dict[str, str]:
    """Deletes files."""
    project_root = get_valid_project_root(req.project_path, dm)
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@fs_router.post("/api/fs/move")
def api_move(req: FileMoveRequest, dm: DataManager = _dm_dep) -> dict[str, Any]:
    """Moves files to a destination directory."""
    try:
        moved_paths = []
        skipped_paths = []
        for src in req.src_paths:
            src_root = get_valid_project_root(src, dm)
            dst_root = get_valid_project_root(req.dst_dir, dm)

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
            moved_paths.append(FileOps.move_file(src, req.dst_dir))

        if skipped_paths and not moved_paths:
            raise HTTPException(
                status_code=403,
                detail=f"All moves blocked or cross-project: {skipped_paths}",
            )

        return {"status": "ok", "new_paths": moved_paths, "skipped": skipped_paths}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@fs_router.post("/api/fs/save")
def api_save(req: FileSaveRequest, dm: DataManager = _dm_dep) -> dict[str, str]:
    """Saves content to a file."""
    try:
        if not get_valid_project_root(req.path, dm):
            raise HTTPException(status_code=403, detail="Access denied")

        logger.info(f"AUDIT - Saving content to: {req.path}")
        FileOps.save_content(req.path, req.content)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e


@fs_router.post("/api/fs/create")
def api_create(
    req: FileCreateRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Creates a new file or directory."""
    try:
        if not get_valid_project_root(req.parent_path, dm):
            raise HTTPException(status_code=403, detail="Access denied")
        logger.info(
            f"AUDIT - Creating {'dir' if req.is_dir else 'file'}: "
            f"{req.name} in {req.parent_path}"
        )
        return {
            "status": "ok",
            "path": FileOps.create_item(req.parent_path, req.name, req.is_dir),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@fs_router.post("/api/fs/open_os")
def api_open_os(
    req: OpenPathRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Opens a file or directory in the operating system shell."""
    project_root = get_valid_project_root(req.project_path, dm)
    if not project_root:
        raise HTTPException(status_code=403, detail="Access denied")
    if not is_path_safe(req.path, project_root):
        raise HTTPException(status_code=403, detail="Path unsafe")

    target = pathlib.Path(req.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    try:
        FileUtils.open_path_in_os(target)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@fs_router.post("/api/fs/archive")
def api_archive(
    req: FileArchiveRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Archives selected files."""
    try:
        if not get_valid_project_root(req.project_root, dm):
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@fs_router.post("/api/fs/collect_paths")
def collect_paths_api(
    req: PathCollectionRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Collects and formats paths."""
    try:
        if req.project_root and not get_valid_project_root(req.project_root, dm):
            raise HTTPException(status_code=403, detail="Unauthorized project root")

        return {
            "result": FormatUtils.collect_paths(
                req.paths,
                req.project_root,
                req.mode,
                req.separator,
                req.file_prefix,
                req.dir_suffix,
            )
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Path collection error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
