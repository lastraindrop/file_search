"""Action routes — staging, categorization, tools, context, settings."""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from file_cortex_core import (
    ActionBridge,
    ContextFormatter,
    DataManager,
    FileOps,
    FileUtils,
    FormatUtils,
    logger,
)
from routers.common import process_manager, register_process, unregister_process
from routers.schemas import (
    CategorizeRequest,
    GenerateRequest,
    GlobalSettingsRequest,
    ProcessTerminateRequest,
    StageAllRequest,
    StatsRequest,
    ToolExecuteRequest,
)
from routers.services import (
    get_dm,
    get_project_config_for_path,
    get_valid_project_root,
    is_path_safe,
)

action_router = APIRouter()
_dm_dep = Depends(get_dm)


@action_router.post("/api/generate")
def generate_context(
    req: GenerateRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Generates formatted context for files."""
    noise_reducer = dm.config.global_settings.enable_noise_reducer or req.apply_noise_reducer
    if req.project_path:
        root, proj_config = get_project_config_for_path(req.project_path, dm)
        if not root:
            raise HTTPException(
                status_code=403,
                detail="Access denied (Project path not registered)",
            )
        final_root = root
        prompt_prefix = None
        if proj_config and req.template_name:
            prompt_prefix = proj_config.get("prompt_templates", {}).get(
                req.template_name
            )
        if req.export_format == "xml":
            content = ContextFormatter.to_xml(
                req.files,
                root_dir=final_root,
                prompt_prefix=prompt_prefix,
                include_blueprint=req.include_blueprint,
                apply_noise_reducer=noise_reducer,
            )
        else:
            content = ContextFormatter.to_markdown(
                req.files,
                root_dir=final_root,
                prompt_prefix=prompt_prefix,
                apply_noise_reducer=noise_reducer,
            )
    else:
        if req.export_format == "xml":
            content = ContextFormatter.to_xml(
                req.files,
                prompt_prefix=None,
                include_blueprint=req.include_blueprint,
                apply_noise_reducer=noise_reducer,
            )
        else:
            content = ContextFormatter.to_markdown(
                req.files,
                prompt_prefix=None,
                apply_noise_reducer=noise_reducer,
            )

    return {"content": content, "tokens": FormatUtils.estimate_tokens(content)}


@action_router.post("/api/project/stats")
def get_staging_stats(req: StatsRequest, dm: DataManager = _dm_dep) -> dict[str, int]:
    """Gets aggregate token stats for selected files."""
    root = get_valid_project_root(req.project_path, dm) if req.project_path else None

    manual_excludes = []
    use_git = True
    if root:
        proj_data = dm.get_project_data(root)
        ex_str = proj_data.get("excludes", "")
        manual_excludes = [e.lower().strip() for e in ex_str.split() if e.strip()]

    all_files = FileUtils.flatten_paths(req.paths, root, manual_excludes, use_git)

    total_tokens = 0
    for f_str in all_files:
        p = pathlib.Path(f_str)
        if p.is_file() and p.exists() and not FileUtils.is_binary(p):
            try:
                total_tokens += FormatUtils.estimate_tokens(
                    FileUtils.read_text_smart(p, max_bytes=1024 * 1024)
                )
            except Exception as e:
                logger.debug(f"Stats calculation failed for {f_str}: {e}")

    return {"total_tokens": total_tokens, "file_count": len(all_files)}


@action_router.get("/api/global/settings")
def get_global_settings(dm: DataManager = _dm_dep) -> dict[str, Any]:
    """Gets global settings."""
    return dm.config.global_settings.model_dump()


@action_router.post("/api/global/settings")
def update_global_settings(
    req: GlobalSettingsRequest, dm: DataManager = _dm_dep
) -> dict[str, str]:
    """Updates global settings."""
    data = req.model_dump(exclude_unset=True)
    if "settings" in data and isinstance(data["settings"], dict):
        data.update(data.pop("settings"))

    dm.update_global_settings(data)
    return {"status": "ok"}


@action_router.post("/api/actions/stage_all")
def api_stage_all(
    req: StageAllRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Stages all files in a project."""
    root, proj_config = get_project_config_for_path(req.project_path, dm)
    if not root or proj_config is None:
        raise HTTPException(status_code=403, detail="Project not registered")

    manual_excludes = (
        proj_config.get("excludes", "").split() if req.apply_excludes else []
    )

    try:
        items = FileUtils.get_project_items(
            root, manual_excludes, use_gitignore=True, mode=req.mode
        )
        added = dm.batch_stage(root, items)
        return {"status": "ok", "added_count": added}
    except Exception as e:
        logger.exception("Stage All failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@action_router.post("/api/actions/categorize")
def api_categorize(
    req: CategorizeRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Categorizes files into a directory."""
    try:
        if not get_valid_project_root(req.project_path, dm):
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


@action_router.post("/api/actions/execute")
def api_execute_tool(
    req: ToolExecuteRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Executes a custom tool on files."""
    try:
        project_root = get_valid_project_root(req.project_path, dm)
        if not project_root:
            raise HTTPException(status_code=403, detail="Access denied")

        proj_config = dm.get_project_data(req.project_path)
        template = proj_config.get("custom_tools", {}).get(req.tool_name)
        if not template:
            raise HTTPException(status_code=404, detail="Tool template not found")

        results = []
        for p in req.paths:
            if not is_path_safe(p, project_root):
                continue

            try:
                proc = ActionBridge.create_process(template, p, project_root)
                if not register_process(proc.pid, proc):
                    proc.kill()
                    results.append({"path": p, "error": "Too many active processes"})
                    continue

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
                    from file_cortex_core.process_utils import terminate_process

                    terminate_process(proc.pid)
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
                    unregister_process(proc.pid)
            except Exception as e:
                results.append({"path": p, "error": f"Execution failed to start: {e}"})

        return {"status": "ok", "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@action_router.post("/api/actions/terminate")
def api_terminate_process(req: ProcessTerminateRequest) -> dict[str, Any]:
    """Terminates a running process."""
    proc = process_manager.get(req.pid)
    if not proc:
        return {
            "status": "error",
            "msg": "Process not found or already finished",
        }

    logger.info(f"AUDIT - Terminating process {req.pid}")
    try:
        from file_cortex_core.process_utils import terminate_process

        terminate_process(req.pid)
        return {"status": "ok"}
    except Exception as e:
        try:
            os.kill(req.pid, signal.SIGTERM)
            return {"status": "ok", "msg": f"killpg failed: {e}"}
        except Exception:
            pass
        return {"status": "error", "msg": str(e)}
