import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from access import require_admin

from fastapi.responses import FileResponse
public_routes = APIRouter()
admin_routes = APIRouter()

from pydantic import BaseModel

AVATARS_DIR = "/var/lib/atena/avatars"
ACTIVE_FILE = "/var/lib/atena/avatars/active.txt"
os.makedirs(AVATARS_DIR, exist_ok=True)

class ActiveAvatarReq(BaseModel):
    name: str

@admin_routes.get("/api/avatars")
async def get_avatars(_: str = Depends(require_admin)):
    avatars = []
    for item in os.listdir(AVATARS_DIR):
        p = os.path.join(AVATARS_DIR, item)
        if os.path.isdir(p):
            files = os.listdir(p)
            avatars.append({"name": item, "files": files})
    active = ""
    if os.path.exists(ACTIVE_FILE):
        active = open(ACTIVE_FILE).read().strip()
    return {"avatars": avatars, "active": active}

@admin_routes.post("/api/avatars/active")
async def set_active_avatar(req: ActiveAvatarReq, _: str = Depends(require_admin)):
    if not req.name:
        if os.path.exists(ACTIVE_FILE):
            os.remove(ACTIVE_FILE)
    else:
        with open(ACTIVE_FILE, "w") as f:
            f.write(req.name)
    return {"status": "ok"}

@admin_routes.post("/api/avatars/upload")
async def upload_avatar(name: str = Form(...), file: UploadFile = File(...), _: str = Depends(require_admin)):
    if not name.isalnum():
        raise HTTPException(400, "Nome non valido, usa solo lettere e numeri senza spazi")
    p = os.path.join(AVATARS_DIR, name)
    os.makedirs(p, exist_ok=True)
    out_path = os.path.join(p, file.filename)
    with open(out_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"status": "ok", "avatar": name, "file": file.filename}

@admin_routes.delete("/api/avatars/{name}")
async def delete_avatar(name: str, _: str = Depends(require_admin)):
    if not name.isalnum():
        raise HTTPException(400, "Nome non valido")
    p = os.path.join(AVATARS_DIR, name)
    if os.path.exists(p):
        shutil.rmtree(p)
    return {"status": "ok"}

@public_routes.get("/api/avatars/serve/{name}/{filename}")
async def serve_avatar_file(name: str, filename: str):
    if not name.isalnum() or ".." in filename:
        raise HTTPException(400)
    p = os.path.join(AVATARS_DIR, name, filename)
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p)
