from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from pydantic import BaseModel
import uvicorn
import os
import pathlib
import json
import asyncio
from core_logic import DataManager, FileUtils, search_generator, FileOps, PathValidator, ContextFormatter, FormatUtils, ActionBridge, logger

app = FastAPI(title="FileCortex v5.0 API")

# --- Static & Templates ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

data_mgr = DataManager()

# --- Models ---
class ProjectOpenRequest(BaseModel):
    path: str

class GenerateRequest(BaseModel):
    files: list[str]

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
    content: str

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

class CategorizeRequest(BaseModel):
    project_path: str
    paths: list[str]
    category_name: str

class ToolExecuteRequest(BaseModel):
    project_path: str
    paths: list[str]
    tool_name: str

def is_path_safe(target_path: str, project_root: str) -> bool:
    """Delegates to PathValidator for safe traversal checks."""
    return PathValidator.is_safe(target_path, project_root)

def get_valid_project_root(path_str: str) -> str | None:
    """
    Finds the valid project root that contains the given path.
    Returns None if the path is not authorized/outside any project.
    """
    try:
        target = pathlib.Path(path_str).resolve()
        for p_root in data_mgr.data["projects"]:
            root = pathlib.Path(p_root).resolve()
            if root == target or root in target.parents:
                return str(p_root)
    except Exception:
        pass
    return None

def get_project_config_for_path(path_str: str):
    """Retrieves project config if path is within a registered project."""
    root = get_valid_project_root(path_str)
    if not root:
        return None, None
    return root, data_mgr.get_project_data(root)

# --- Helpers ---
def get_node_info(path_obj, project_root):
    """Returns a single node's info (non-recursive) with formatted metadata."""
    rel = path_obj.relative_to(project_root) if project_root in path_obj.parents or project_root == path_obj else path_obj.name
    meta = FileUtils.get_metadata(path_obj)
    
    mtime_fmt = FormatUtils.format_datetime(meta["mtime"])
    
    return {
        "name": path_obj.name,
        "path": str(path_obj),
        "type": "dir" if path_obj.is_dir() else "file",
        "has_children": path_obj.is_dir() and any(os.scandir(path_obj)) if path_obj.is_dir() else False,
        "mtime_fmt": mtime_fmt,
        "size_fmt": FormatUtils.format_size(meta["size"]),
        **meta
    }

def get_children(path_str):
    path = pathlib.Path(path_str)
    if not path.exists() or not path.is_dir(): return []
    
    # NEW: Secure project root resolution
    project_root_str = get_valid_project_root(path_str)
    if not project_root_str:
        logger.warning(f"Blocking potentially unsafe path access: {path_str}")
        return []
    
    project_root = pathlib.Path(project_root_str)
    proj_config = data_mgr.get_project_data(project_root_str)
    excludes = proj_config.get("excludes", "").split()
    git_spec = FileUtils.get_gitignore_spec(project_root_str)

    children = []
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries:
            rel = pathlib.Path(entry.path).relative_to(project_root)
            if FileUtils.should_ignore(entry.name, rel, excludes, git_spec):
                continue
            children.append(get_node_info(pathlib.Path(entry.path), project_root))
    except PermissionError:
        logger.error(f"Permission denied for directory: {path_str}")
    except Exception as e:
        logger.error(f"Error listing children for {path_str}: {e}")
    return children

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/open")
async def open_project(req: ProjectOpenRequest):
    try:
        # Register project in data_mgr to allow safe path access
        p = PathValidator.validate_project(req.path)
        logger.info(f"AUDIT - Opening project: {p}")
        data_mgr.data["last_project"] = str(p)
        data_mgr.get_project_data(str(p))
        data_mgr.save()
        
        # Returns only root info
        root_node = get_node_info(p, p)
        return {"status": "ok", "name": p.name, "root": root_node}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/children")
async def api_children(req: ChildrenRequest):
    children = get_children(req.path)
    return {"status": "ok", "children": children}

@app.get("/api/content")
async def get_content(path: str):
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
        # Read max 100KB for preview
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return {"content": f.read(100000)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

@app.post("/api/generate")
async def generate_context(req: GenerateRequest):
    content = ContextFormatter.to_markdown(req.files)
    return {"content": content}

# --- File Operations APIs ---
@app.post("/api/fs/rename")
async def rename_file(req: FileRenameRequest):
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

@app.post("/api/fs/delete")
async def delete_files(req: FileDeleteRequest):
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
async def api_move(req: FileMoveRequest):
    try:
        moved_paths = []
        for src in req.src_paths:
            # Safety Check for src and dst
            src_root = get_valid_project_root(src)
            dst_root = get_valid_project_root(req.dst_dir)

            if not src_root or not dst_root:
                 logger.warning(f"Blocking potentially unsafe move: {src} -> {req.dst_dir}")
                 continue

            logger.info(f"AUDIT - Moving: {src} -> {req.dst_dir}")
            new_path = FileOps.move_file(src, req.dst_dir)
            moved_paths.append(new_path)
        return {"status": "ok", "new_paths": moved_paths}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/save")
async def api_save(req: FileSaveRequest):
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
async def api_create(req: FileCreateRequest):
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
async def api_archive(req: FileArchiveRequest):
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
async def get_proj_config(path: str):
    if not is_path_safe(path, path): # Basic existence check
         raise HTTPException(status_code=403, detail="Invalid path")
    return data_mgr.get_project_data(path)

@app.get("/api/recent_projects")
async def get_recent_projects():
    return [{"path": p, "name": os.path.basename(p)} for p in data_mgr.data["projects"].keys() if os.path.exists(p)]

@app.post("/api/project/note")
async def api_add_note(req: NoteRequest):
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    data_mgr.add_note(req.project_path, req.file_path, req.note)
    return {"status": "ok"}

@app.post("/api/project/tag")
async def api_manage_tag(req: TagRequest):
    if not is_path_safe(req.file_path, req.project_path):
        raise HTTPException(status_code=403, detail="Path unsafe")
    if req.action == "add":
        data_mgr.add_tag(req.project_path, req.file_path, req.tag)
    else:
        data_mgr.remove_tag(req.project_path, req.file_path, req.tag)
    return {"status": "ok"}

@app.post("/api/project/session")
async def api_save_session(req: SessionRequest):
    data_mgr.save_session(req.project_path, req.data)
    return {"status": "ok"}

@app.post("/api/project/favorites")
async def api_manage_favorites(req: FavoriteRequest):
    if req.action == "add":
        data_mgr.add_to_group(req.project_path, req.group_name, req.file_paths)
    else:
        data_mgr.remove_from_group(req.project_path, req.group_name, req.file_paths)
    return {"status": "ok"}

@app.post("/api/project/settings")
async def update_settings(req: ProjectSettingsRequest):
    data_mgr.update_project_settings(req.project_path, req.settings)
    return {"status": "ok"}

# --- FileCortex Action APIs ---
@app.post("/api/actions/categorize")
async def api_categorize(req: CategorizeRequest):
    try:
        if not get_valid_project_root(req.project_path):
            raise HTTPException(status_code=403, detail="Access denied")
        
        logger.info(f"AUDIT - Batch categorizing {len(req.paths)} items to '{req.category_name}'")
        moved = FileOps.batch_categorize(req.project_path, req.paths, req.category_name)
        return {"status": "ok", "moved_count": len(moved), "paths": moved}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/actions/execute")
async def api_execute_tool(req: ToolExecuteRequest):
    try:
        project_root = get_valid_project_root(req.project_path)
        if not project_root:
            raise HTTPException(status_code=403, detail="Access denied")
        
        proj_config = data_mgr.get_project_data(req.project_path)
        template = proj_config["custom_tools"].get(req.tool_name)
        if not template:
            raise HTTPException(status_code=404, detail="Tool template not found")
        
        results = []
        for p in req.paths:
            if not is_path_safe(p, project_root):
                continue
            res = ActionBridge.execute_tool(template, p, project_root)
            results.append({"path": p, **res})
            
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- WebSocket Search ---
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
    
    def run_search():
        try:
            # Pass inverse and case_sensitive to search_generator
            for res_dict in search_generator(p, query, mode, excludes, 
                                            include_dirs=False, 
                                            is_inverse=inverse,
                                            case_sensitive=case_sensitive):
                # Use call_soon_threadsafe to put results into the main loop's queue
                main_loop.call_soon_threadsafe(result_queue.put_nowait, {
                    "name": os.path.basename(res_dict["path"]),
                    "path": res_dict["path"],
                    "type": res_dict["match_type"],
                    "size": res_dict["size"],
                    "mtime": res_dict["mtime"],
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
        print("Client disconnected")
    except Exception as e:
        print(f"Search error: {e}")
        try:
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
        except: pass

if __name__ == "__main__":
    print("Starting Web Server...")
    # Open browser automatically?
    # import webbrowser
    # webbrowser.open("http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)