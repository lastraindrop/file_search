"""WebSocket routes for the FileCortex web application."""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import threading
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from file_cortex_core import ActionBridge, DataManager, FormatUtils, logger, search_generator
from routers.common import register_process, unregister_process
from routers.services import (
    get_dm,
    get_project_config_for_path,
    get_valid_project_root,
    is_path_safe,
)

router = APIRouter()
_dm_dep = Depends(get_dm)

def verify_ws_token(token: str | None) -> bool:
    """Verifies the API token for WebSocket connections (constant-time)."""
    expected_token = os.getenv("FCTX_API_TOKEN", "")
    if not expected_token:
        return True
    if not token:
        return False
    import hmac
    return hmac.compare_digest(token, expected_token)


@router.websocket("/ws/search")
async def websocket_search(
    websocket: WebSocket,
    path: str,
    query: str,
    token: str | None = Query(None),
    mode: str = "smart",
    inverse: bool = False,
    case_sensitive: bool = False,
    include_dirs: bool = False,
    dm: DataManager = _dm_dep,
) -> None:
    """Streams search results over WebSocket."""
    await websocket.accept()

    if not verify_ws_token(token):
        await websocket.send_json({"status": "ERROR", "msg": "Unauthorized"})
        await websocket.close()
        return

    project_root, proj_config = get_project_config_for_path(path, dm)
    if not project_root or proj_config is None:
        logger.warning(f"Blocking potentially unsafe search access: {path}")
        await websocket.send_json(
            {"status": "ERROR", "msg": "Access denied (Path unsafe)"}
        )
        await websocket.close()
        return

    p = pathlib.Path(path)
    excludes = proj_config.get("excludes", "")

    result_queue: asyncio.Queue[dict[str, Any] | str] = asyncio.Queue()
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
                include_dirs=include_dirs,
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
                        "snippet": res_dict.get("snippet", ""),
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
    except Exception as e:
        logger.exception("Search error")
        with contextlib.suppress(Exception):
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
    finally:
        # BUG-W4 fix: always cancel + await search_task to prevent orphan threads.
        search_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await search_task


@router.websocket("/ws/actions/execute")
async def websocket_action_stream(
    websocket: WebSocket,
    project_path: str,
    tool_name: str,
    path: str,
    token: str | None = Query(None),
    dm: DataManager = _dm_dep,
) -> None:
    """Streams tool execution output over WebSocket."""
    await websocket.accept()

    if not verify_ws_token(token):
        await websocket.send_json({"status": "ERROR", "msg": "Unauthorized"})
        await websocket.close()
        return

    project_root = get_valid_project_root(project_path, dm)
    if not project_root:
        await websocket.send_json({"status": "ERROR", "msg": "Access denied"})
        await websocket.close()
        return

    proj_config = dm.get_project_data(project_path)
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
    result_queue: asyncio.Queue[dict[str, Any] | str] = asyncio.Queue()
    main_loop = asyncio.get_running_loop()

    def run_stream() -> None:
        proc = None
        try:
            proc = ActionBridge.create_process(template, path, project_root)
            current_pid[0] = proc.pid
            if not register_process(proc.pid, proc):
                main_loop.call_soon_threadsafe(
                    result_queue.put_nowait, {"error": "Too many active processes"}
                )
                main_loop.call_soon_threadsafe(result_queue.put_nowait, "DONE")
                return

            main_loop.call_soon_threadsafe(result_queue.put_nowait, {"pid": proc.pid})

            if proc.stdout:
                for line in proc.stdout:
                    main_loop.call_soon_threadsafe(result_queue.put_nowait, {"out": line})

            proc.wait()
            unregister_process(proc.pid)
            main_loop.call_soon_threadsafe(
                result_queue.put_nowait, {"exit_code": proc.returncode}
            )
        except Exception as e:
            main_loop.call_soon_threadsafe(result_queue.put_nowait, {"error": str(e)})
        finally:
            if proc and proc.pid:
                unregister_process(proc.pid)
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
                from file_cortex_core.process_utils import terminate_process

                terminate_process(pid)

                unregister_process(pid)
            except Exception:
                logger.exception(f"Cleanup failed for pid {pid}")
    except Exception as e:
        logger.exception("Action stream error")
        with contextlib.suppress(Exception):
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
    finally:
        stream_task.cancel()
