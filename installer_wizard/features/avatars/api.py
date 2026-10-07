import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from access import require_admin

public_routes = APIRouter()
admin_routes = APIRouter()

AVATARS_DIR = "/var/lib/atena/avatars"
os.makedirs(AVATARS_DIR, exist_ok=True)

@admin_routes.get("/api/avatars")
async def get_avatars(_: str = Depends(require_admin)):
    avatars = []
    for item in os.listdir(AVATARS_DIR):
        p = os.path.join(AVATARS_DIR, item)
        if os.path.isdir(p):
            files = os.listdir(p)
            avatars.append({"name": item, "files": files})
    return {"avatars": avatars}

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
