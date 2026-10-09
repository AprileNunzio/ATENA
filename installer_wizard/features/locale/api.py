import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from access import NO_CACHE, is_local, require_admin, require_display, session_user
from config import UI_LANGUAGES

from features.locale import service
from features.locale.machine import machine
from features.voices import languages

public_routes = APIRouter()
admin_routes = APIRouter()
DEVICE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def device_of(request: Request) -> str:
    return "kiosk" if is_local(request) else "remote"


def _snapshot(ui: str, device: str = "") -> dict:
    reply = service.chosen(device=device) if device else None
    return {"ui": ui, "system_ui": service.system_ui(), "ui_languages": UI_LANGUAGES,
            "reply": reply.lang if reply else service.system_reply(), "teach": bool(reply and reply.teach),
            "reply_languages": {code: native for code, (_, native, _) in languages.LANGS.items()}}


async def _body(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Richiesta non valida")
    return body


@public_routes.get("/api/locale")
async def public_locale(request: Request):
    device = device_of(request)
    return JSONResponse(_snapshot(service.ui_lang(device=device), device), headers=NO_CACHE)


@public_routes.put("/api/locale/ui")
async def public_set_ui(request: Request):
    require_display(request)
    try:
        return {"ui": service.set_ui(str((await _body(request)).get("lang") or ""), device=device_of(request))}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.get("/api/locale")
async def admin_locale(request: Request, user: str = Depends(require_admin)):
    return JSONResponse(_snapshot(service.ui_lang(user=user)), headers=NO_CACHE)


@admin_routes.put("/api/locale/ui")
async def admin_set_ui(request: Request, user: str = Depends(require_admin)):
    try:
        return {"ui": service.set_ui(str((await _body(request)).get("lang") or ""), user=user)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.put("/api/locale/device/{device}")
async def admin_set_device(device: str, request: Request, _: str = Depends(require_admin)):
    if not DEVICE.match(device):
        raise HTTPException(400, "Dispositivo non valido")
    body = await _body(request)
    try:
        if "ui" in body:
            service.set_ui(str(body.get("ui") or ""), device=device)
        if body.get("reply"):
            service.choose(str(body["reply"]), bool(body.get("teach")), device=device)
        elif "reply" in body:
            service.forget_choice(device=device)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _snapshot(service.ui_lang(device=device), device)


def page_language(request: Request, admin: bool) -> str:
    if admin:
        user = session_user(request)
        return service.ui_lang(user=user) if user else service.system_ui()
    return service.ui_lang(device=device_of(request))


@admin_routes.get("/i18n/catalog/{lang}")
@public_routes.get("/i18n/catalog/{lang}")
async def ui_catalog(lang: str):
    try:
        return JSONResponse(machine.view(lang), headers=NO_CACHE)
    except KeyError:
        raise HTTPException(404, "Lingua non disponibile")
