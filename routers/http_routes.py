"""HTTP routes for the FileCortex web application."""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException

from file_cortex_core import (
    ActionBridge,
    ContextFormatter,
    FileOps,
    FileUtils,
    FormatUtils,
    PathValidator,
    logger,
)
from routers.common import (
    ACTIVE_PROCESSES,
    PROCESS_LOCK,
    BatchRenameRequest,
    CategoriesUpdateRequest,
    CategorizeRequest,
    ChildrenRequest,
    FavoriteRequest,
    FileArchiveRequest,
    FileCreateRequest,
    FileDeleteRequest,
    FileMoveRequest,
    FileRenameRequest,
    FileSaveRequest,
    GenerateRequest,
    GlobalSettingsRequest,
    NoteRequest,
    OpenPathRequest,
    PathCollectionRequest,
    ProcessTerminateRequest,
    ProjectOpenRequest,
    ProjectSettingsRequest,
    SessionRequest,
    StageAllRequest,
    StatsRequest,
    TagRequest,
    ToolExecuteRequest,
    ToolsUpdateRequest,
    WorkspacePinRequest,
    get_children,
    get_dm,
    get_node_info,
    get_project_config_for_path,
    get_valid_project_root,
    is_path_safe,
)

router = APIRouter()


@router.post("/api/open")
def open_project(req: ProjectOpenRequest) -> dict[str, Any]:
    """Opens and registers a project."""
    try:
        p = PathValidator.validate_project(req.path)
        logger.info(f"AUDIT - Opening project: {p}")
        dm = get_dm()

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


@router.post("/api/fs/children")
def api_children(req: ChildrenRequest) -> dict[str, Any]:
    """Gets directory children."""
    p = pathlib.Path(req.path)
    if not get_valid_project_root(req.path):
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "status": "ok",
        "parent": PathValidator.norm_path(p.parent) if p.parent else None,
        "children": get_children(req.path),
    }


@router.get("/api/content")
def get_content(path: str) -> dict[str, Any]:
    """Gets file content for preview."""
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
        dm = get_dm()
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
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}") from e


@router.post("/api/generate")
def generate_context(req: GenerateRequest) -> dict[str, Any]:
    """Generates formatted context for files."""
    if req.project_path:
        root, proj_config = get_project_config_for_path(req.project_path)
        final_root = root if root else req.project_path
        prompt_prefix = None
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

    return {"content": content, "tokens": FormatUtils.estimate_tokens(content)}


@router.post("/api/fs/rename")
def rename_file(req: FileRenameRequest) -> dict[str, Any]:
    """Renames a file."""
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/fs/batch_rename")
def api_batch_rename(req: BatchRenameRequest) -> dict[str, Any]:
    """Batch renames files."""
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/fs/delete")
def delete_files(req: FileDeleteRequest) -> dict[str, str]:
    """Deletes files."""
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/fs/move")
def api_move(req: FileMoveRequest) -> dict[str, Any]:
    """Moves files to a destination directory."""
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


@router.post("/api/fs/save")
def api_save(req: FileSaveRequest) -> dict[str, str]:
    """Saves content to a file."""
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/fs/create")
def api_create(req: FileCreateRequest) -> dict[str, Any]:
    """Creates a new file or directory."""
    try:
        if not get_valid_project_root(req.parent_path):
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


@router.post("/api/fs/open_os")
def api_open_os(req: OpenPathRequest) -> dict[str, str]:
    """Opens a file or directory in the operating system shell."""
    project_root = get_valid_project_root(req.project_path)
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


@router.get("/api/config/global")
def get_global_config() -> dict[str, Any]:
    """Gets global configuration."""
    return get_dm().data["global_settings"]


@router.post("/api/config/global")
def update_global_config(req: GlobalSettingsRequest) -> dict[str, Any]:
    """Updates global configuration."""
    data = req.model_dump(exclude_unset=True)
    if "settings" in data and isinstance(data["settings"], dict):
        data.update(data.pop("settings"))

    get_dm().update_global_settings(data)
    return {"status": "ok", "settings": get_dm().data["global_settings"]}


@router.post("/api/fs/archive")
def api_archive(req: FileArchiveRequest) -> dict[str, str]:
    """Archives selected files."""
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/project/config")
def get_proj_config(path: str) -> dict[str, Any]:
    """Gets project configuration."""
    root, _ = get_project_config_for_path(path)
    if not root:
        raise HTTPException(status_code=403, detail="Access denied")
    return get_dm().get_project_data(root)


@router.get("/api/project/prompt_templates")
def get_prompt_templates(path: str) -> dict[str, str]:
    """Gets project prompt templates."""
    root, proj_config = get_project_config_for_path(path)
    if not root or proj_config is None:
        return {}
    return proj_config.get("prompt_templates", {})


@router.get("/api/workspaces")
def get_workspaces() -> dict[str, Any]:
    """Gets all workspaces."""
    return get_dm().get_workspaces_summary()


@router.post("/api/workspaces/pin")
def toggle_pin(req: WorkspacePinRequest) -> dict[str, bool]:
    """Toggles workspace pin status."""
    return {"is_pinned": get_dm().toggle_pinned(req.path)}


@router.get("/api/recent_projects")
def get_recent_projects_legacy() -> list[dict[str, str]]:
    """Gets recent projects using the legacy response shape."""
    return [
        {"name": pathlib.Path(p).name, "path": p}
        for p in get_dm().data["projects"].keys()
        if p and os.path.exists(p)
    ]


@router.post("/api/project/note")
def api_add_note(req: NoteRequest) -> dict[str, str]:
    """Adds a note to a file."""
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    get_dm().add_note(req.project_path, req.file_path, req.note)
    return {"status": "ok"}


@router.post("/api/project/tag")
def api_manage_tag(req: TagRequest) -> dict[str, str]:
    """Manages tags on a file."""
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    if req.action == "add":
        get_dm().add_tag(req.project_path, req.file_path, req.tag)
    else:
        get_dm().remove_tag(req.project_path, req.file_path, req.tag)
    return {"status": "ok"}


@router.post("/api/project/session")
def api_save_session(req: SessionRequest) -> dict[str, str]:
    """Saves a project session."""
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    get_dm().save_session(req.project_path, req.data)
    return {"status": "ok"}


@router.post("/api/project/favorites")
def api_manage_favorites(req: FavoriteRequest) -> dict[str, str]:
    """Manages favorite groups."""
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    for file_path in req.file_paths:
        if not is_path_safe(file_path, req.project_path):
            raise HTTPException(status_code=403, detail=f"Path unsafe: {file_path}")
    if req.action == "add":
        get_dm().add_to_group(req.project_path, req.group_name, req.file_paths)
    else:
        get_dm().remove_from_group(req.project_path, req.group_name, req.file_paths)
    return {"status": "ok"}


@router.post("/api/project/settings")
def update_settings(req: ProjectSettingsRequest) -> dict[str, str]:
    """Updates project settings."""
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    get_dm().update_project_settings(req.project_path, req.settings)
    return {"status": "ok"}


@router.post("/api/project/tools")
def update_tools(req: ToolsUpdateRequest) -> dict[str, str]:
    """Updates custom tools configuration."""
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        get_dm().update_custom_tools(req.project_path, req.tools)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/project/stats")
def get_staging_stats(req: StatsRequest) -> dict[str, int]:
    """Gets aggregate token stats for selected files."""
    root = get_valid_project_root(req.project_path) if req.project_path else None

    manual_excludes = []
    use_git = True
    if root:
        proj_data = get_dm().get_project_data(root)
        ex_str = proj_data.get("excludes", "")
        manual_excludes = [e.lower().strip() for e in ex_str.split() if e.strip()]

    all_files = FileUtils.flatten_paths(req.paths, root, manual_excludes, use_git)

    total_tokens = 0
    for f_str in all_files:
        p = pathlib.Path(f_str)
        if p.is_file() and p.exists() and not FileUtils.is_binary(p):
            try:
                total_tokens += FormatUtils.estimate_tokens(FileUtils.read_text_smart(p))
            except Exception as e:
                logger.debug(f"Stats calculation failed for {f_str}: {e}")

    return {"total_tokens": total_tokens, "file_count": len(all_files)}


@router.post("/api/project/categories")
def update_categories(req: CategoriesUpdateRequest) -> dict[str, str]:
    """Updates quick categories."""
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        get_dm().update_quick_categories(req.project_path, req.categories)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/global/settings")
def get_global_settings() -> dict[str, Any]:
    """Gets global settings."""
    return get_dm().data.get("global_settings", {})


@router.post("/api/global/settings")
def update_global_settings(req: GlobalSettingsRequest) -> dict[str, str]:
    """Updates global settings."""
    data = req.model_dump(exclude_unset=True)
    if "settings" in data and isinstance(data["settings"], dict):
        data.update(data.pop("settings"))

    get_dm().update_global_settings(data)
    return {"status": "ok"}


@router.post("/api/actions/stage_all")
def api_stage_all(req: StageAllRequest) -> dict[str, Any]:
    """Stages all files in a project."""
    root, proj_config = get_project_config_for_path(req.project_path)
    if not root or proj_config is None:
        raise HTTPException(status_code=403, detail="Project not registered")

    manual_excludes = (
        proj_config.get("excludes", "").split() if req.apply_excludes else []
    )

    try:
        items = FileUtils.get_project_items(
            root, manual_excludes, use_gitignore=True, mode=req.mode
        )
        added = get_dm().batch_stage(root, items)
        return {"status": "ok", "added_count": added}
    except Exception as e:
        logger.error(f"Stage All failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/actions/categorize")
def api_categorize(req: CategorizeRequest) -> dict[str, Any]:
    """Categorizes files into a directory."""
    try:
        if not get_valid_project_root(req.project_path):
            raise HTTPException(status_code=403, detail="Access denied")

        logger.info(
            f"AUDIT - Batch categorizing {len(req.paths)} items "
            f"to '{req.category_name}'"
        )
        moved = FileOps.batch_categorize(req.project_path, req.paths, req.category_name)
        return {"status": "ok", "moved_count": len(moved), "paths": moved}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/actions/execute")
def api_execute_tool(req: ToolExecuteRequest) -> dict[str, Any]:
    """Executes a custom tool on files."""
    try:
        project_root = get_valid_project_root(req.project_path)
        if not project_root:
            raise HTTPException(status_code=403, detail="Access denied")

        proj_config = get_dm().get_project_data(req.project_path)
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
                    proc.communicate()
                    results.append(
                        {
                            "path": p,
                            "error": (
                                f"Command timed out after {exec_timeout} seconds"
                            ),
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/fs/collect_paths")
def collect_paths_api(req: PathCollectionRequest) -> dict[str, str]:
    """Collects and formats paths."""
    try:
        if req.project_root and not get_valid_project_root(req.project_root):
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


@router.post("/api/actions/terminate")
def api_terminate_process(req: ProcessTerminateRequest) -> dict[str, Any]:
    """Terminates a running process."""
    with PROCESS_LOCK:
        proc = ACTIVE_PROCESSES.get(req.pid)
        if not proc:
            return {
                "status": "error",
                "msg": "Process not found or already finished",
            }

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
