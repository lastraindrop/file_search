"""WebSocket routes for the FileCortex web application."""

from __future__ import annotations

import asyncio
import os
import pathlib
import signal
import subprocess
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from file_cortex_core import ActionBridge, FormatUtils, logger, search_generator
from routers.common import (
    ACTIVE_PROCESSES,
    PROCESS_LOCK,
    get_dm,
    get_project_config_for_path,
    get_valid_project_root,
    is_path_safe,
)

router = APIRouter()


@router.websocket("/ws/search")
async def websocket_search(
    websocket: WebSocket,
    path: str,
    query: str,
    mode: str = "smart",
    inverse: bool = False,
    case_sensitive: bool = False,
    include_dirs: bool = False,
) -> None:
    """Streams search results over WebSocket."""
    await websocket.accept()

    project_root, proj_config = get_project_config_for_path(path)
    if not project_root or proj_config is None:
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


@router.websocket("/ws/actions/execute")
async def websocket_action_stream(
    websocket: WebSocket,
    project_path: str,
    tool_name: str,
    path: str,
) -> None:
    """Streams tool execution output over WebSocket."""
    await websocket.accept()

    project_root = get_valid_project_root(project_path)
    if not project_root:
        await websocket.send_json({"status": "ERROR", "msg": "Access denied"})
        await websocket.close()
        return

    proj_config = get_dm().get_project_data(project_path)
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
