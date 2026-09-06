"""WebSocket routes for the FileCortex web application."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import os
import pathlib
import threading
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from file_cortex_core import (
    ActionBridge,
    DataManager,
    FormatUtils,
    PathValidator,
    logger,
    search_generator,
)
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
    # Encode before comparing: non-ASCII tokens would raise TypeError
    # inside compare_digest(str, str).
    return hmac.compare_digest(
        token.encode("utf-8"), expected_token.encode("utf-8")
    )


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
    if not verify_ws_token(token):
        # Accept the handshake first: calling close() before accept() makes
        # Starlette reject the upgrade with a bare HTTP 403 and the custom
        # code 4001 never reaches the client.
        await websocket.accept()
        await websocket.close(code=4001)
        return

    await websocket.accept()

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

    result_queue: asyncio.Queue[dict[str, Any] | str] = asyncio.Queue(maxsize=100)
    main_loop = asyncio.get_running_loop()
    stop_event = threading.Event()

    def enqueue(item: dict[str, Any] | str) -> bool:
        """Applies backpressure when the WebSocket consumer is slow."""
        while not stop_event.is_set():
            future = asyncio.run_coroutine_threadsafe(result_queue.put(item), main_loop)
            try:
                future.result(timeout=0.1)
                return True
            except (TimeoutError, concurrent.futures.TimeoutError):
                # NOTE: on Python 3.10 concurrent.futures.TimeoutError is NOT
                # the builtin TimeoutError (unified in 3.11); catch both so
                # backpressure still works on the 3.10 support tier.
                future.cancel()
        return False

    def run_search() -> None:
        try:
            # B6: align the fallback with ProjectConfig.max_search_size_mb
            # (10). The dict always carries the key in practice, but the
            # fallback must not contradict the documented default.
            max_size = proj_config.get("max_search_size_mb", 10)
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
                if not enqueue({
                    # Normalize like every other path the frontend receives
                    # (tree nodes, staging_list) so search-result staging does
                    # not create duplicate entries differing only by separator.
                    "path": PathValidator.norm_path(res_dict["path"]),
                    "name": os.path.basename(res_dict["path"]),
                    "type": res_dict["match_type"],
                    "size": res_dict["size"],
                    "size_fmt": FormatUtils.format_size(res_dict["size"]),
                    "mtime": res_dict["mtime"],
                    "mtime_fmt": res_dict.get("mtime_fmt", ""),
                    "ext": res_dict["ext"],
                    "snippet": res_dict.get("snippet", ""),
                }):
                    break
        except Exception as e:
            # A mid-scan crash must not be mistaken for a normal completion:
            # the finally clause below always enqueues DONE, so report the
            # failure explicitly (mirrors run_stream's error handling).
            logger.exception("Background search thread failed")
            enqueue({"status": "ERROR", "msg": str(e)})
        finally:
            enqueue("DONE")

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
        # Always signal the background search thread to stop, not just on
        # WebSocketDisconnect. Without this, a generic exception path leaves
        # the sync generator scanning the disk until it naturally completes.
        stop_event.set()
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
    if not verify_ws_token(token):
        # Accept before close so the 4001 code actually reaches the client
        # (same rationale as the /ws/search handler).
        await websocket.accept()
        await websocket.close(code=4001)
        return

    await websocket.accept()

    project_root = get_valid_project_root(project_path, dm)
    if not project_root:
        await websocket.send_json({"status": "ERROR", "msg": "Access denied"})
        await websocket.close()
        return

    proj_config = dm.get_project_data(project_path)
    # Defensive lookup: legacy/malformed configs may lack the `custom_tools` key.
    # Falls through to the 'Tool template not found' error path instead of KeyError.
    template = proj_config.get("custom_tools", {}).get(tool_name)
    if not template:
        await websocket.send_json({"status": "ERROR", "msg": "Tool template not found"})
        await websocket.close()
        return

    if not is_path_safe(path, project_root):
        await websocket.send_json({"status": "ERROR", "msg": "Path unsafe"})
        await websocket.close()
        return

    current_pid = [None]
    stop_event = threading.Event()
    result_queue: asyncio.Queue[dict[str, Any] | str] = asyncio.Queue(maxsize=100)
    main_loop = asyncio.get_running_loop()

    def enqueue(item: dict[str, Any] | str) -> bool:
        """Blocks the reader thread instead of accumulating unlimited output."""
        while not stop_event.is_set():
            future = asyncio.run_coroutine_threadsafe(result_queue.put(item), main_loop)
            try:
                future.result(timeout=0.1)
                return True
            except (TimeoutError, concurrent.futures.TimeoutError):
                # Python 3.10 compatibility: concurrent.futures.TimeoutError
                # is a distinct type there (unified with TimeoutError in 3.11).
                future.cancel()
        return False

    def terminate_current_process() -> None:
        if not current_pid[0]:
            return
        try:
            from file_cortex_core.process_utils import terminate_process

            terminate_process(current_pid[0])
            unregister_process(current_pid[0])
        except Exception:
            logger.exception(f"Cleanup failed for pid {current_pid[0]}")

    def run_stream() -> None:
        proc = None
        try:
            proc = ActionBridge.create_process(template, path, project_root)
            current_pid[0] = proc.pid
            if not register_process(proc.pid, proc):
                # Capacity exceeded: the process was already spawned by
                # create_process, so it must be terminated to avoid an
                # orphan/leaked subprocess.
                try:
                    proc.kill()
                except Exception:
                    logger.exception("Failed to kill unregistered process")
                enqueue({"error": "Too many active processes"})
                return

            enqueue({"pid": proc.pid})

            if proc.stdout:
                for line in proc.stdout:
                    if not enqueue({"out": line}):
                        terminate_current_process()
                        return

            proc.wait()
            unregister_process(proc.pid)
            enqueue({"exit_code": proc.returncode})
        except Exception as e:
            enqueue({"error": str(e)})
        finally:
            if proc and proc.pid:
                unregister_process(proc.pid)
            enqueue("DONE")

    stream_task = asyncio.create_task(asyncio.to_thread(run_stream))

    try:
        while True:
            res = await result_queue.get()
            if res == "DONE":
                await websocket.send_json({"status": "DONE"})
                break
            await websocket.send_json(res)
    except WebSocketDisconnect:
        stop_event.set()
        if current_pid[0]:
            logger.info(f"AUDIT - Terminating abandoned process {current_pid[0]}")
            terminate_current_process()
    except Exception as e:
        logger.exception("Action stream error")
        with contextlib.suppress(Exception):
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
    finally:
        stop_event.set()
        terminate_current_process()
        stream_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await stream_task
