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
from core_logic import DataManager, FileUtils, search_generator, FileOps

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

# --- Helpers ---
def get_node_info(path_obj, project_root):
    """Returns a single node's info (non-recursive)."""
    rel = path_obj.relative_to(project_root) if project_root in path_obj.parents or project_root == path_obj else path_obj.name
    return {
        "name": path_obj.name,
        "path": str(path_obj),
        "type": "dir" if path_obj.is_dir() else "file",
        "has_children": path_obj.is_dir() and any(os.scandir(path_obj)) if path_obj.is_dir() else False
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
    for p_root in data_mgr.data["projects"]:
        if path_str.startswith(p_root):
            project_root = pathlib.Path(p_root)
            break

    proj_config = data_mgr.get_project_data(str(project_root))
    excludes = proj_config.get("excludes", "").split()
    git_spec = FileUtils.get_gitignore_spec(project_root)

    children = []
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries:
            rel = pathlib.Path(entry.path).relative_to(project_root)
            if FileUtils.should_ignore(entry.name, rel, excludes, git_spec):
                continue
            children.append(get_node_info(pathlib.Path(entry.path), project_root))
    except PermissionError: pass
    return children

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/open")
async def open_project(req: ProjectOpenRequest):
    p = pathlib.Path(req.path)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail="Invalid directory path")
    
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
    if not p.exists() or not p.is_file():
        return {"content": "File not found"}
    if FileUtils.is_binary(p):
        return {"content": "--- Binary File (Preview Unavailable) ---"}
    try:
        # Read max 100KB for preview
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return {"content": f.read(100000)}
    except Exception as e:
        return {"content": f"Error reading file: {e}"}

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
async def api_rename(req: FileRenameRequest):
    try:
        new_path = FileOps.rename_file(req.path, req.new_name)
        return {"status": "ok", "new_path": new_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/delete")
async def api_delete(req: FileDeleteRequest):
    try:
        for p in req.paths:
            FileOps.delete_file(p)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/move")
async def api_move(req: FileMoveRequest):
    try:
        moved_paths = []
        for src in req.src_paths:
            new_path = FileOps.move_file(src, req.dst_dir)
            moved_paths.append(new_path)
        return {"status": "ok", "new_paths": moved_paths}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fs/save")
async def api_save(req: FileSaveRequest):
    try:
        FileOps.save_content(req.path, req.content)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- WebSocket Search ---
@app.websocket("/ws/search")
async def websocket_search(websocket: WebSocket, path: str, query: str, mode: str = "smart", 
                           inverse: bool = False, case_sensitive: bool = False):
    await websocket.accept()
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
            for result_path, match_type in search_generator(p, query, mode, excludes, 
                                                            include_dirs=False, 
                                                            is_inverse=inverse,
                                                            case_sensitive=case_sensitive):
                # Use call_soon_threadsafe to put results into the main loop's queue
                main_loop.call_soon_threadsafe(result_queue.put_nowait, {
                    "name": os.path.basename(result_path),
                    "path": result_path,
                    "type": match_type
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