from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.requests import Request
from pydantic import BaseModel, Field
import uvicorn
import os
import pathlib
import json
import asyncio
from file_cortex_core import DataManager, FileUtils, search_generator, FileOps, PathValidator, ContextFormatter, FormatUtils, ActionBridge, logger
import signal
import threading
import subprocess

app = FastAPI(title="FileCortex v5.8.2 API")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Fallback handler for unhandled server-side exceptions."""
    logger.error(f"Global Unhandled Exception: {exc}", exc_info=True)
    
    # Hide internal details in production
    detail = f"Internal Server Error: {str(exc)}"
    if os.getenv("FCTX_PROD") == "1":
        detail = "Internal Server Error. Please check server logs for details."
        
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": detail}
    )

# --- Global State ---
ACTIVE_PROCESSES = {} # { pid: process_obj }
PROCESS_LOCK = threading.Lock()

# --- Static & Templates ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Use Singleton inside routes rather than a global variable to ensure test isolation
def _get_dm(): return DataManager()

# --- Models ---
class ProjectOpenRequest(BaseModel):
    path: str

class StageAllRequest(BaseModel):
    project_path: str
    mode: str = "files" # "files" or "top_folders"
    apply_excludes: bool = True

class GenerateRequest(BaseModel):
    files: list[str]
    project_path: str | None = None
    template_name: str | None = None
    export_format: str = "markdown" # "markdown" or "xml"

class FileRenameRequest(BaseModel):
    project_path: str
    path: str
    new_name: str

class FileDeleteRequest(BaseModel):
    project_path: str
    paths: list[str]

class FileMoveRequest(BaseModel):
    src_paths: list[str]
    dst_dir: str

class FileSaveRequest(BaseModel):
    path: str
    content: str = Field(..., max_length=10_000_000) # Limit to 10MB to prevent OOM

class FileCreateRequest(BaseModel):
    parent_path: str
    name: str
    is_dir: bool = False

class FileArchiveRequest(BaseModel):
    paths: list[str]
    output_name: str
    project_root: str

class ChildrenRequest(BaseModel):
    path: str

class NoteRequest(BaseModel):
    project_path: str
    file_path: str
    note: str

class TagRequest(BaseModel):
    project_path: str
    file_path: str
    tag: str
    action: str  # "add" or "remove"

class GlobalSettingsRequest(BaseModel):
    settings: dict

class FavoriteRequest(BaseModel):
    project_path: str
    group_name: str
    file_paths: list[str]
    action: str # "add" or "remove"

class SessionRequest(BaseModel):
    project_path: str
    data: dict

class ProjectSettingsRequest(BaseModel):
    project_path: str
    settings: dict

class ToolsUpdateRequest(BaseModel):
    project_path: str
    tools: dict  # {name: command_template}

class CategoriesUpdateRequest(BaseModel):
    project_path: str
    categories: dict  # {name: relative_target_dir}

class PathCollectionRequest(BaseModel):
    paths: list[str]
    project_root: str | None = None
    mode: str = "relative" # "relative" or "absolute"
    separator: str = "\n"
    file_prefix: str = ""
    dir_suffix: str = ""

class WorkspacePinRequest(BaseModel):
    path: str

class CategorizeRequest(BaseModel):
    project_path: str
    paths: list[str]
    category_name: str

class StatsRequest(BaseModel):
    paths: list[str]
    project_path: str | None = None

class ToolExecuteRequest(BaseModel):
    project_path: str
    paths: list[str]
    tool_name: str

class BatchRenameRequest(BaseModel):
    project_path: str
    paths: list[str]
    pattern: str
    replacement: str
    dry_run: bool = True

class ProcessTerminateRequest(BaseModel):
    pid: int

def is_path_safe(target_path: str, project_root: str) -> bool:
    """Delegates to PathValidator for safe traversal checks."""
    return PathValidator.is_safe(target_path, project_root)

def get_valid_project_root(path_str: str) -> str | None:
    """Delegates to DataManager for authorized project root discovery."""
    return _get_dm().resolve_project_root(path_str)

def get_project_config_for_path(path_str: str):
    """Retrieves project config if path is within a registered project."""
    root = get_valid_project_root(path_str)
    if not root:
        return None, None
    return root, _get_dm().get_project_data(root)

# --- Helpers ---
def _has_children(path_obj):
    """Safely check if directory has children."""
    try:
        with os.scandir(path_obj) as it:
            return any(it)
    except (PermissionError, OSError):
        return False

def get_node_info(path_obj, project_root):
    """Returns a single node's info (non-recursive) with formatted metadata."""
    is_d = path_obj.is_dir()
    meta = FileUtils.get_metadata(path_obj)
    mtime_fmt = FormatUtils.format_datetime(meta["mtime"])
    
    return {
        "name": path_obj.name,
        "path": PathValidator.norm_path(path_obj),
        "type": "dir" if is_d else "file",
        "has_children": is_d and _has_children(path_obj),
        "mtime_fmt": mtime_fmt,
        "size_fmt": FormatUtils.format_size(meta["size"]),
        "size": meta["size"],
        "mtime": meta["mtime"],
        "ext": meta["ext"]
    }

def get_children(path_str):
    path = pathlib.Path(path_str)
    if not path.exists() or not path.is_dir(): return []
    
    # NEW: Secure project root resolution
    # Safety Check
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
                    if norm_entry.startswith(norm_root.rstrip('/') + '/'):
                        rel = pathlib.Path(norm_entry[len(norm_root):].lstrip('/'))
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

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/open")
def open_project(req: ProjectOpenRequest):
    try:
        # Register project in data_mgr to allow safe path access
        p = PathValidator.validate_project(req.path)
        logger.info(f"AUDIT - Opening project: {p}")
        dm = _get_dm()
        
        # New: Tracking workspace high-level history
        dm.add_to_recent(str(p))
        dm.get_project_data(str(p))
        dm.save()
        
        # Returns only root info
        root_node = get_node_info(p, p)
        return root_node
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/children")
def api_children(req: ChildrenRequest):
    p = pathlib.Path(req.path)
    children = get_children(req.path)
    return {
        "status": "ok", 
        "parent": PathValidator.norm_path(p.parent) if p.parent else None,
        "children": children
    }

@app.get("/api/content")
def get_content(path: str):
    p = pathlib.Path(path)
    
    # Safety Check: Must be within a known project
    if not get_valid_project_root(path):
        logger.warning(f"Blocking unauthorized content access: {path}")
        raise HTTPException(status_code=403, detail="Access denied (Path not within any project root)")

    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    if FileUtils.is_binary(p):
        return {"content": "--- Binary File (Preview Unavailable) ---"}
    try:
        # CR-A01 Fix: Use read_text_smart for consistent encoding detection
        # We increase max_bytes to 1MB for browsing, and provide truncation hint
        MAX_PREVIEW = 1000000
        content = FileUtils.read_text_smart(p, max_bytes=MAX_PREVIEW)
        
        # Determine encoding (approximate from smart reader)
        # In a real scenario, read_text_smart would return this. For now, we assume utf-8 or detected.
        return {
            "content": content,
            "encoding": "utf-8", # Simplified; read_text_smart handles it internally
            "is_truncated": len(content.encode('utf-8', errors='ignore')) >= MAX_PREVIEW
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

@app.post("/api/generate")
def generate_context(req: GenerateRequest):
    root, proj_config = None, None
    prompt_prefix = None
    if req.project_path:
        root, proj_config = get_project_config_for_path(req.project_path)
        # Fallback to req.project_path itself if it's the root of the files
        final_root = root if root else req.project_path
        if proj_config and req.template_name:
            prompt_prefix = proj_config.get("prompt_templates", {}).get(req.template_name)
        if req.export_format == "xml":
            content = ContextFormatter.to_xml(req.files, root_dir=final_root, prompt_prefix=prompt_prefix)
        else:
            content = ContextFormatter.to_markdown(req.files, root_dir=final_root, prompt_prefix=prompt_prefix)
    else:
        if req.export_format == "xml":
            content = ContextFormatter.to_xml(req.files, prompt_prefix=None)
        else:
            content = ContextFormatter.to_markdown(req.files, prompt_prefix=None)
    tokens = FormatUtils.estimate_tokens(content)
    return {"content": content, "tokens": tokens}

# --- File Operations APIs ---
@app.post("/api/fs/rename")
def rename_file(req: FileRenameRequest):
    project_root = get_valid_project_root(req.project_path)
    if not project_root:
        raise HTTPException(status_code=403, detail="Access denied (Invalid project path)")
        
    if not is_path_safe(req.path, project_root):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Path Traversal Check: Ensure new_name is just a name, not a path
    if any(sep in req.new_name for sep in (os.sep, '/')):
        raise HTTPException(status_code=400, detail="Invalid characters in new name")

    try:
        logger.info(f"AUDIT - Renaming: {req.path} -> {req.new_name}")
        new_path = FileOps.rename_file(req.path, req.new_name)
        return {"status": "ok", "new_path": new_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/batch_rename")
def api_batch_rename(req: BatchRenameRequest):
    project_root = get_valid_project_root(req.project_path)
    if not project_root:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Safety Check: all paths must be safe
    for p in req.paths:
        if not is_path_safe(p, project_root):
            raise HTTPException(status_code=403, detail=f"Path unsafe: {p}")
            
    try:
        logger.info(f"AUDIT - Batch Renaming ({'Dry' if req.dry_run else 'Live'}): {len(req.paths)} items")
        results = FileOps.batch_rename(req.project_path, req.paths, req.pattern, req.replacement, req.dry_run)
        return {"status": "ok", "results": results}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fs/delete")
def delete_files(req: FileDeleteRequest):
    project_root = get_valid_project_root(req.project_path)
    if not project_root:
        raise HTTPException(status_code=403, detail="Access denied (Invalid project path)")

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
def api_move(req: FileMoveRequest):
    try:
        moved_paths = []
        skipped_paths = []
        for src in req.src_paths:
            # Safety Check for src and dst
            src_root = get_valid_project_root(src)
            dst_root = get_valid_project_root(req.dst_dir)

            if not src_root or not dst_root:
                 logger.warning(f"Blocking potentially unsafe move: {src} -> {req.dst_dir}")
                 skipped_paths.append(src)
                 continue
            
            # Cross-project move prevention
            if PathValidator.norm_path(src_root) != PathValidator.norm_path(dst_root):
                logger.warning(f"Blocking cross-project move: {src} ({src_root}) -> {req.dst_dir} ({dst_root})")
                skipped_paths.append(src)
                continue

            logger.info(f"AUDIT - Moving: {src} -> {req.dst_dir}")
            new_path = FileOps.move_file(src, req.dst_dir)
            moved_paths.append(new_path)
        
        if skipped_paths and not moved_paths:
            raise HTTPException(status_code=403, detail=f"All moves blocked or cross-project: {skipped_paths}")
            
        return {"status": "ok", "new_paths": moved_paths, "skipped": skipped_paths}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/save")
def api_save(req: FileSaveRequest):
    try:
        # Safety Check: Must be within a known project
        if not get_valid_project_root(req.path):
             raise HTTPException(status_code=403, detail="Access denied")

        logger.info(f"AUDIT - Saving content to: {req.path}")
        FileOps.save_content(req.path, req.content)
        return {"status": "ok"}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Save error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/create")
def api_create(req: FileCreateRequest):
    try:
        if not get_valid_project_root(req.parent_path):
             raise HTTPException(status_code=403, detail="Access denied")
        logger.info(f"AUDIT - Creating {'dir' if req.is_dir else 'file'}: {req.name} in {req.parent_path}")
        new_path = FileOps.create_item(req.parent_path, req.name, req.is_dir)
        return {"status": "ok", "path": new_path}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/archive")
def api_archive(req: FileArchiveRequest):
    try:
        # project_root itself must be safe
        if not get_valid_project_root(req.project_root):
             raise HTTPException(status_code=403, detail="Access denied")
        
        for p in req.paths:
            if not is_path_safe(p, req.project_root):
                raise HTTPException(status_code=403, detail=f"Unsafe path: {p}")
        
        # Ensure output_name is just a name, not a path to prevent traversal
        if any(sep in req.output_name for sep in (os.sep, '/')):
            raise HTTPException(status_code=400, detail="Invalid characters in output name")

        logger.info(f"AUDIT - Archiving {len(req.paths)} items to {req.output_name} in {req.project_root}")
        output_file = os.path.join(req.project_root, req.output_name)
        result_path = FileOps.archive_selection(req.paths, output_file, req.project_root)
        return {"status": "ok", "archive_path": result_path}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Workspace Memory APIs ---
@app.get("/api/project/config")
def get_proj_config(path: str):
    if not get_valid_project_root(path):
         raise HTTPException(status_code=403, detail="Access denied")
    return _get_dm().get_project_data(path)

@app.get("/api/project/prompt_templates")
def get_prompt_templates(path: str):
    root, proj_config = get_project_config_for_path(path)
    if not root or proj_config is None:
         # H8 Fix: Graceful handling for missing project configuration
         return {}
    return proj_config.get("prompt_templates", {})

@app.get("/api/workspaces")
def get_workspaces():
    return _get_dm().get_workspaces_summary()

@app.post("/api/workspaces/pin")
def toggle_pin(req: WorkspacePinRequest):
    status = _get_dm().toggle_pinned(req.path)
    return {"is_pinned": status}

@app.get("/api/recent_projects")
def get_recent_projects_legacy():
    # Keep for old UI compatibility during migration if needed, but we'll update UI soon
    # M14 Fix: Secure path check
    return [{"name": pathlib.Path(p).name, "path": p} for p in _get_dm().data["projects"].keys() if p and os.path.exists(p)]


@app.post("/api/project/note")
def api_add_note(req: NoteRequest):
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    _get_dm().add_note(req.project_path, req.file_path, req.note)
    return {"status": "ok"}

@app.post("/api/project/tag")
def api_manage_tag(req: TagRequest):
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    if req.action == "add":
        _get_dm().add_tag(req.project_path, req.file_path, req.tag)
    else:
        _get_dm().remove_tag(req.project_path, req.file_path, req.tag)
    return {"status": "ok"}

@app.post("/api/project/session")
def api_save_session(req: SessionRequest):
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    _get_dm().save_session(req.project_path, req.data)
    return {"status": "ok"}

@app.post("/api/project/favorites")
def api_manage_favorites(req: FavoriteRequest):
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    if req.action == "add":
        _get_dm().add_to_group(req.project_path, req.group_name, req.file_paths)
    else:
        _get_dm().remove_from_group(req.project_path, req.group_name, req.file_paths)
    return {"status": "ok"}

@app.post("/api/project/settings")
def update_settings(req: ProjectSettingsRequest):
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    _get_dm().update_project_settings(req.project_path, req.settings)
    return {"status": "ok"}

@app.post("/api/project/tools")
def update_tools(req: ToolsUpdateRequest):
    """Dedicated endpoint for updating custom_tools (separated from settings for RCE prevention)."""
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        _get_dm().update_custom_tools(req.project_path, req.tools)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/stats")
def get_staging_stats(req: StatsRequest):
    """Calculates total token estimate for a list of paths, including recursive expansion."""
    root = get_valid_project_root(req.project_path) if req.project_path else None
    
    # Get configuration for excludes if project is valid
    manual_excludes = []
    use_git = True
    if root:
        proj_data = _get_dm().get_project_data(root)
        ex_str = proj_data.get("excludes", "")
        manual_excludes = [e.lower().strip() for e in ex_str.split() if e.strip()]

    # Flatten paths to include all files in directories (De-duplicate & Expand)
    all_files = FileUtils.flatten_paths(req.paths, root, manual_excludes, use_git)
    
    total_tokens = 0
    for f_str in all_files:
        p = pathlib.Path(f_str)
        if p.is_file() and p.exists() and not FileUtils.is_binary(p):
            try:
                # Use read_text_smart for efficiency and OOM protection
                content = FileUtils.read_text_smart(p)
                total_tokens += FormatUtils.estimate_tokens(content)
            except Exception as e:
                logger.debug(f"Stats calculation failed for {f_str}: {e}")
                
    return {
        "total_tokens": total_tokens,
        "file_count": len(all_files)
    }

@app.post("/api/project/categories")
def update_categories(req: CategoriesUpdateRequest):
    """Dedicated endpoint for updating quick_categories (separated from settings for security)."""
    if not get_valid_project_root(req.project_path):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        _get_dm().update_quick_categories(req.project_path, req.categories)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/global/settings")
def get_global_settings():
    return _get_dm().data.get("global_settings", {})

@app.post("/api/global/settings")
def update_global_settings(req: GlobalSettingsRequest):
    _get_dm().update_global_settings(req.settings)
    return {"status": "ok"}

# --- FileCortex Action APIs ---

@app.post("/api/actions/stage_all")
def api_stage_all(req: StageAllRequest):
    root, proj_config = get_project_config_for_path(req.project_path)
    if not root:
        raise HTTPException(status_code=403, detail="Project not registered")
    
    manual_excludes = proj_config.get("excludes", "").split() if req.apply_excludes else []
    
    try:
        items = FileUtils.get_project_items(root, manual_excludes, use_gitignore=True, mode=req.mode)
        added = _get_dm().batch_stage(root, items)
        return {"status": "ok", "added_count": added}
    except Exception as e:
        logger.error(f"Stage All failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/actions/categorize")
def api_categorize(req: CategorizeRequest):
    try:
        if not get_valid_project_root(req.project_path):
            raise HTTPException(status_code=403, detail="Access denied")
        
        logger.info(f"AUDIT - Batch categorizing {len(req.paths)} items to '{req.category_name}'")
        moved = FileOps.batch_categorize(req.project_path, req.paths, req.category_name)
        return {"status": "ok", "moved_count": len(moved), "paths": moved}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/actions/execute")
def api_execute_tool(req: ToolExecuteRequest):
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
            
            # Use Popen-based execution for consistency and potential termination tracking
            try:
                proc = ActionBridge.create_process(template, p, project_root)
                with PROCESS_LOCK:
                    ACTIVE_PROCESSES[proc.pid] = proc
                
                try:
                    # CR-B02 Fix: Use configurable timeout to avoid test hangs
                    exec_timeout = int(os.getenv("FCTX_EXEC_TIMEOUT", "300"))
                    stdout, stderr = proc.communicate(timeout=exec_timeout)
                    
                    results.append({
                        "path": p, 
                        "stdout": stdout, 
                        "stderr": stderr, 
                        "exit_code": proc.returncode,
                        "pid": proc.pid
                    })
                except subprocess.TimeoutExpired:
                    # CR-B02 Fix: Assassinate zombie process on timeout to release file handles
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    stdout, stderr = proc.communicate() # Drain pipes
                    results.append({"path": p, "error": f"Command timed out after {exec_timeout} seconds"})
                except Exception as e:
                    proc.kill()
                    results.append({"path": p, "error": f"Process error: {e}"})
                finally:
                    with PROCESS_LOCK:
                        ACTIVE_PROCESSES.pop(proc.pid, None)
            except Exception as e:
                # Execution start failed (e.g. shlex split error)
                results.append({"path": p, "error": f"Execution failed to start: {e}"})
            
        return {"status": "ok", "results": results}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- WebSocket Search ---
@app.post("/api/fs/collect_paths")
def collect_paths_api(req: PathCollectionRequest):
    """
    Format a list of paths into a single string with custom separators.
    """
    try:
        # Valid Project Root Check for safety
        # CR-08 Fix: Implement real project validation if root is provided
        if req.project_root:
            if not get_valid_project_root(req.project_root):
                 raise HTTPException(status_code=403, detail="Unauthorized project root")
        
        res = FormatUtils.collect_paths(req.paths, req.project_root, req.mode, req.separator, req.file_prefix, req.dir_suffix)
        return {"result": res}
    except Exception as e:
        logger.error(f"Path collection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/actions/terminate")
def api_terminate_process(req: ProcessTerminateRequest):
    with PROCESS_LOCK:
        proc = ACTIVE_PROCESSES.get(req.pid)
        if proc:
            logger.info(f"AUDIT - Terminating process {req.pid}")
            try:
                if os.name == 'nt':
                    # Use taskkill to ensure child processes are also handled on Windows
                    # M5 Fix: Removed redundant import subprocess
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(req.pid)], capture_output=True)
                else:
                    # Kill entire process group on Unix
                    os.killpg(os.getpgid(req.pid), signal.SIGTERM)
                return {"status": "ok"}
            except Exception as e:
                # Fallback to single PID signal if killpg fails (unlikely if created correctly)
                try: 
                    os.kill(req.pid, signal.SIGTERM)
                    return {"status": "ok", "msg": f"killpg failed, used fallback kill: {e}"}
                except: pass
                return {"status": "error", "msg": str(e)}
        else:
            return {"status": "error", "msg": "Process not found or already finished"}

@app.websocket("/ws/search")
async def websocket_search(websocket: WebSocket, path: str, query: str, mode: str = "smart", 
                           inverse: bool = False, case_sensitive: bool = False):
    await websocket.accept()
    
    # Safety Check
    project_root, proj_config = get_project_config_for_path(path)
            
    if not project_root:
        logger.warning(f"Blocking potentially unsafe search access: {path}")
        await websocket.send_json({"status": "ERROR", "msg": "Access denied (Path unsafe)"})
        await websocket.close()
        return

    p = pathlib.Path(path)
    excludes = proj_config.get("excludes", "")

    # Use a thread-safe queue to bridge synchronous generator and async websocket
    result_queue = asyncio.Queue()
    main_loop = asyncio.get_running_loop()
    
    # Use a threading.Event to bridge sync cancellation
    stop_event = threading.Event()
    
    def run_search():
        try:
            # Pass inverse and case_sensitive to search_generator
            max_size = proj_config.get("max_search_size_mb", 5)
            for res_dict in search_generator(p, query, mode, excludes, 
                                            include_dirs=False, 
                                            is_inverse=inverse,
                                            case_sensitive=case_sensitive,
                                            max_size_mb=max_size,
                                            stop_event=stop_event):
                if stop_event.is_set(): break
                # Use call_soon_threadsafe to put results into the main loop's queue
                main_loop.call_soon_threadsafe(result_queue.put_nowait, {
                    "name": os.path.basename(res_dict["path"]),
                    "path": res_dict["path"],
                    "type": res_dict["match_type"],
                    "size": res_dict["size"],
                    "mtime": res_dict["mtime"],
                    "mtime_fmt": res_dict.get("mtime_fmt", ""),
                    "ext": res_dict["ext"]
                })
        finally:
            main_loop.call_soon_threadsafe(result_queue.put_nowait, "DONE")

    # Start search in a background thread
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
        except Exception: pass

@app.websocket("/ws/actions/execute")
async def websocket_action_stream(websocket: WebSocket, project_path: str, tool_name: str, path: str):
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

    # Check path safety
    if not is_path_safe(path, project_root):
        await websocket.send_json({"status": "ERROR", "msg": "Path unsafe"})
        await websocket.close()
        return

    current_pid = [None]

    def run_stream():
        proc = None
        try:
            proc = ActionBridge.create_process(template, path, project_root)
            current_pid[0] = proc.pid
            # Register process for potential termination
            with PROCESS_LOCK:
                ACTIVE_PROCESSES[proc.pid] = proc
            
            # Send PID to frontend immediately
            main_loop.call_soon_threadsafe(result_queue.put_nowait, {"pid": proc.pid})
            
            for line in proc.stdout:
                main_loop.call_soon_threadsafe(result_queue.put_nowait, {"out": line})
            
            proc.wait()
            with PROCESS_LOCK:
                ACTIVE_PROCESSES.pop(proc.pid, None)
            main_loop.call_soon_threadsafe(result_queue.put_nowait, {"exit_code": proc.returncode})
        except Exception as e:
            main_loop.call_soon_threadsafe(result_queue.put_nowait, {"error": str(e)})
        finally:
            if proc and proc.pid:
                with PROCESS_LOCK:
                    ACTIVE_PROCESSES.pop(proc.pid, None)
            main_loop.call_soon_threadsafe(result_queue.put_nowait, "DONE")

    result_queue = asyncio.Queue()
    main_loop = asyncio.get_running_loop()
    stream_task = asyncio.create_task(asyncio.to_thread(run_stream))

    try:
        while True:
            res = await result_queue.get()
            if res == "DONE":
                await websocket.send_json({"status": "DONE"})
                break
            await websocket.send_json(res)
    except WebSocketDisconnect:
        # Crucial Hardening: Kill the process if user closes the socket before it finishes
        if current_pid[0]:
            pid = current_pid[0]
            logger.info(f"AUDIT - Terminating abandoned process {pid} due to WebSocket disconnect")
            try:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
                else:
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

def main():
    import argparse
    parser = argparse.ArgumentParser(description="FileCortex Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    
    uvicorn.run("web_app:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()