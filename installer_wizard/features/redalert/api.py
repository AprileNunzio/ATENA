import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from access import NO_CACHE, require_admin
from features.redalert.broadcast import clips
from features.redalert.service import redalert

public_routes = APIRouter()
admin_routes = APIRouter()
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


@public_routes.get("/api/redalert/audio/{token}.wav")
async def redalert_audio(token: str):
    wav = clips.get(token) if TOKEN_RE.match(token) else None
    if wav is None:
        raise HTTPException(404, "Messaggio scaduto")
    return Response(wav, media_type="audio/wav", headers=NO_CACHE)


@admin_routes.post("/api/redalert/test")
async def redalert_test(user: str = Depends(require_admin)):
    if not redalert.trigger(f"Prova dell'allarme richiesta da {user}: nessun pericolo.", 12):
        raise HTTPException(409, "L'allarme rosso è disattivato")
    return {"ok": True}


@admin_routes.post("/api/redalert/stop")
async def redalert_stop(_: str = Depends(require_admin)):
    redalert.stop()
    return {"ok": True}
