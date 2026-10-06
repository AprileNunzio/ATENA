from fastapi import APIRouter, Depends, HTTPException, Request

import packages
from access import require_admin
from settings import apply_config, normalize_ollama

admin_routes = APIRouter()

BRAIN_STEPS = {"local": ["ollama", "models", "brain", "warmup"], "remote": ["models", "warmup"], "cloud": []}


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "Richiesta non valida")
    return data if isinstance(data, dict) else {}


@admin_routes.get("/api/packages")
async def list_packages(_: str = Depends(require_admin)):
    return {"brain": packages.brain_mode(), "packages": packages.catalog()}


@admin_routes.post("/api/packages/brain")
async def set_brain(request: Request, user: str = Depends(require_admin)):
    data = await _body(request)
    mode = str(data.get("mode", ""))
    if mode not in packages.BRAIN_MODES:
        raise HTTPException(400, "Modalità del cervello non valida")
    updates = {"ATENA_BRAIN": mode}
    if mode == "remote":
        url = normalize_ollama(str(data.get("url", "")))
        if not url:
            raise HTTPException(400, "Indica l'indirizzo del server Ollama")
        updates["ATENA_OLLAMA_URL"] = url
    elif mode == "local":
        updates["ATENA_OLLAMA_URL"] = ""
    applying = await apply_config(updates, user, BRAIN_STEPS[mode])
    return {"ok": True, "brain": mode, "applying": applying}


@admin_routes.post("/api/packages/{pkg_id}")
async def set_package(pkg_id: str, request: Request, user: str = Depends(require_admin)):
    data = await _body(request)
    on = data.get("on") is True
    try:
        updates = packages.request_updates(pkg_id, on)
    except KeyError:
        raise HTTPException(404, "Pacchetto sconosciuto o non rimovibile")
    pkg = packages.PACKAGE_BY_ID[pkg_id]
    steps = list(pkg.steps) + (BRAIN_STEPS["local"] if pkg_id == "brain_local" else [])
    applying = await apply_config(updates, user, steps)
    return {"ok": True, "applying": applying, "packages": packages.catalog()}
