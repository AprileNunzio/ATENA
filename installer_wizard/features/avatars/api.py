import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from access import require_admin
from config import STATE_DIR

from fastapi.responses import FileResponse
public_routes = APIRouter()
admin_routes = APIRouter()

from pydantic import BaseModel

AVATARS_DIR = STATE_DIR / "avatars"
ACTIVE_FILE = AVATARS_DIR / "active.txt"
AVATARS_DIR.mkdir(parents=True, exist_ok=True)

class ActiveAvatarReq(BaseModel):
    name: str

@admin_routes.get("/api/avatars")
async def get_avatars(_: str = Depends(require_admin)):
    avatars = []
    for item in AVATARS_DIR.iterdir():
        if item.is_dir():
            avatars.append({"name": item.name, "files": [f.name for f in item.iterdir()]})
    active = ""
    if ACTIVE_FILE.exists():
        active = ACTIVE_FILE.read_text(encoding="utf-8").strip()
    return {"avatars": avatars, "active": active}

@admin_routes.post("/api/avatars/active")
async def set_active_avatar(req: ActiveAvatarReq, _: str = Depends(require_admin)):
    if not req.name:
        if ACTIVE_FILE.exists():
            ACTIVE_FILE.unlink()
    else:
        ACTIVE_FILE.write_text(req.name, encoding="utf-8")
    return {"status": "ok"}

@admin_routes.post("/api/avatars/upload")
async def upload_avatar(name: str = Form(...), file: UploadFile = File(...), _: str = Depends(require_admin)):
    if not name.isalnum():
        raise HTTPException(400, "Nome non valido, usa solo lettere e numeri senza spazi")
    p = AVATARS_DIR / name
    p.mkdir(parents=True, exist_ok=True)
    out_path = p / file.filename
    with open(out_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"status": "ok", "avatar": name, "file": file.filename}

@admin_routes.delete("/api/avatars/{name}")
async def delete_avatar(name: str, _: str = Depends(require_admin)):
    if not name.isalnum():
        raise HTTPException(400, "Nome non valido")
    p = AVATARS_DIR / name
    if p.exists():
        shutil.rmtree(p)
    return {"status": "ok"}

@public_routes.get("/api/avatars/serve/{name}/{filename}")
async def serve_avatar_file(name: str, filename: str):
    if not name.isalnum() or ".." in filename:
        raise HTTPException(400)
    p = AVATARS_DIR / name / filename
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)
