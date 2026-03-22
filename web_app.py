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
from core_logic import DataManager, FileUtils, search_generator, FileOps, logger

app = FastAPI(title="AI Context Workbench Web")

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
    path: str
    new_name: str

class FileDeleteRequest(BaseModel):
    paths: list[str]

class FileMoveRequest(BaseModel):
    src_paths: list[str]
    dst_dir: str

class FileSaveRequest(BaseModel):
    path: str
    content: str

class ChildrenRequest(BaseModel):
    path: str

def is_path_safe(target_path: str, project_root: str) -> bool:
    """Checks if the target path is within the project root to prevent traversal."""
    try:
        t = pathlib.Path(target_path).resolve()
        r = pathlib.Path(project_root).resolve()
        return r in t.parents or r == t
    except:
        return False

# --- Helpers ---
def get_node_info(path_obj, project_root):
    """Returns a single node's info (non-recursive)."""
    rel = path_obj.relative_to(project_root) if project_root in path_obj.parents or project_root == path_obj else path_obj.name
    meta = FileUtils.get_metadata(path_obj)
    return {
        "name": path_obj.name,
        "path": str(path_obj),
        "type": "dir" if path_obj.is_dir() else "file",
        "has_children": path_obj.is_dir() and any(os.scandir(path_obj)) if path_obj.is_dir() else False,
        **meta
    }

def get_children(path_str):
    path = pathlib.Path(path_str)
    if not path.exists() or not path.is_dir(): return []
    
    # We need the project root to check ignore rules correctly
    # For now, let's assume the path is within a project we can find in data_mgr
    # or just use the path itself if no better context.
    # In a real app, you'd track the "current project root" in the session or request.
    project_root = path
    # Try to find the closest project root from data_mgr
    project_root = None
    for p_root in data_mgr.data["projects"]:
        if path_str.startswith(p_root):
            project_root = pathlib.Path(p_root)
            break
            
    if not project_root:
        # Fallback to the path itself or parent if not in a known project
        project_root = path if path.is_dir() else path.parent

    if not is_path_safe(path_str, str(project_root)):
        logger.warning(f"Blocking potentially unsafe path access: {path_str}")
        return []

    proj_config = data_mgr.get_project_data(str(project_root))
    excludes = proj_config.get("excludes", "").split()
    git_spec = FileUtils.get_gitignore_spec(str(project_root))

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
    p = pathlib.Path(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Path does not exist")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="Invalid directory path")
    
    # Register project in data_mgr to allow safe path access
    data_mgr.data["last_project"] = str(p)
    data_mgr.get_project_data(str(p))
    data_mgr.save()
    
    # Returns only root info
    root_node = get_node_info(p, p)
    return {"status": "ok", "name": p.name, "root": root_node}

@app.post("/api/fs/children")
async def api_children(req: ChildrenRequest):
    children = get_children(req.path)
    return {"status": "ok", "children": children}

@app.get("/api/content")
async def get_content(path: str):
    p = pathlib.Path(path)
    
    # Safety Check: Must be within a known project
    valid_root = None
    for p_root in data_mgr.data["projects"]:
        if is_path_safe(path, p_root):
            valid_root = p_root
            break
            
    if not valid_root:
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
    final = []
    for f in req.files:
        p = pathlib.Path(f)
        if p.exists() and p.is_file():
            if FileUtils.is_binary(p): continue
            try:
                text = p.read_text('utf-8', 'ignore')
                block = f"File: {p.name}\n```{FileUtils.get_language_tag(p.suffix)}\n{text}\n```\n\n"
                final.append(block)
            except: pass
    return {"content": "".join(final)}

# --- File Operations APIs ---
@app.post("/api/fs/rename")
async def rename_file(req: FileRenameRequest):
    project_root = data_mgr.data.get("last_project")
    if not project_root or not is_path_safe(req.path, project_root):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check new path for traversal
    new_path_full = os.path.join(os.path.dirname(req.path), req.new_name)
    if not is_path_safe(new_path_full, project_root):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        new_path = FileOps.rename_file(req.path, req.new_name)
        return {"status": "ok", "new_path": new_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/delete")
async def delete_files(req: FileDeleteRequest):
    project_root = data_mgr.data.get("last_project")
    if not project_root:
        raise HTTPException(status_code=403, detail="No project open to perform delete operation.")

    try:
        for p in req.paths:
            if not is_path_safe(p, project_root):
                logger.warning(f"Blocking potentially unsafe delete access: {p}")
                raise HTTPException(status_code=403, detail=f"Access denied for {p}")
            FileOps.delete_file(p)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/move")
async def api_move(req: FileMoveRequest):
    try:
        moved_paths = []
        for src in req.src_paths:
            # Safety Check for src
            src_project_root = None
            for p_root in data_mgr.data["projects"]:
                if src.startswith(p_root):
                    src_project_root = p_root
                    break
            
            # Safety Check for dst
            dst_project_root = None
            for p_root in data_mgr.data["projects"]:
                if req.dst_dir.startswith(p_root):
                    dst_project_root = p_root
                    break

            if not src_project_root or not is_path_safe(src, src_project_root) or \
               not dst_project_root or not is_path_safe(req.dst_dir, dst_project_root):
                 logger.warning(f"Blocking potentially unsafe move: {src} -> {req.dst_dir}")
                 continue

            new_path = FileOps.move_file(src, req.dst_dir)
            moved_paths.append(new_path)
        return {"status": "ok", "new_paths": moved_paths}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/save")
async def api_save(req: FileSaveRequest):
    try:
        # Safety Check: Must be within a known project
        valid_root = None
        for p_root in data_mgr.data["projects"]:
            if is_path_safe(req.path, p_root):
                valid_root = p_root
                break

        if not valid_root:
             raise HTTPException(status_code=403, detail="Access denied (Path not within any project root)")

        FileOps.save_content(req.path, req.content)
        return {"status": "ok"}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Save error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# --- WebSocket Search ---
@app.websocket("/ws/search")
async def websocket_search(websocket: WebSocket, path: str, query: str, mode: str = "smart", 
                           inverse: bool = False, case_sensitive: bool = False):
    await websocket.accept()
    
    # Safety Check
    project_root = None
    for p_root in data_mgr.data["projects"]:
        if path.startswith(p_root):
            project_root = p_root
            break
            
    if not project_root or not is_path_safe(path, project_root):
        logger.warning(f"Blocking potentially unsafe search access: {path}")
        await websocket.send_json({"status": "ERROR", "msg": "Access denied (Path unsafe)"})
        await websocket.close()
        return

    p = pathlib.Path(path)
    
    # Get config for excludes
    proj_config = data_mgr.get_project_data(str(p))
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