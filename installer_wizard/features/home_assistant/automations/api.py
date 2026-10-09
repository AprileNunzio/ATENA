from access import require_admin
from fastapi import APIRouter, Depends, HTTPException, Request
from state import store

from features.home_assistant import home
from features.home_assistant.automations.generate import draft
from features.home_assistant.automations.model import AutomationError
from features.home_assistant.automations.service import AutomationService

admin_routes = APIRouter()
automations = AutomationService(home.brain)


def _fail(exc: AutomationError):
    raise HTTPException(400, str(exc))


def _online() -> None:
    if not home.brain.online:
        raise HTTPException(409, "Home Assistant non è collegato")


@admin_routes.get("/api/home/automations")
async def ha_automations(_: str = Depends(require_admin)):
    _online()
    return {"automations": await automations.overview()}


@admin_routes.get("/api/home/automations/{entity_id}")
async def ha_automation(entity_id: str, _: str = Depends(require_admin)):
    _online()
    try:
        return await automations.get(entity_id)
    except AutomationError as exc:
        _fail(exc)


@admin_routes.post("/api/home/automations")
async def ha_automation_create(request: Request, user: str = Depends(require_admin)):
    _online()
    try:
        saved = await automations.save(None, (await request.json()).get("config"))
    except AutomationError as exc:
        _fail(exc)
    store.event("INFO", f"Automazione di Home Assistant «{saved['config']['alias']}» creata da {user}", "home")
    return saved


@admin_routes.put("/api/home/automations/id/{auto_id}")
async def ha_automation_save(auto_id: str, request: Request, user: str = Depends(require_admin)):
    _online()
    try:
        saved = await automations.save(auto_id, (await request.json()).get("config"))
    except AutomationError as exc:
        _fail(exc)
    store.event("INFO", f"Automazione di Home Assistant «{saved['config']['alias']}» modificata da {user}", "home")
    return saved


@admin_routes.delete("/api/home/automations/id/{auto_id}")
async def ha_automation_delete(auto_id: str, user: str = Depends(require_admin)):
    _online()
    try:
        await automations.delete(auto_id)
    except AutomationError as exc:
        _fail(exc)
    store.event("INFO", f"Automazione di Home Assistant {auto_id} eliminata da {user}", "home")
    return {"ok": True}


@admin_routes.get("/api/home/automations/id/{auto_id}/traces")
async def ha_automation_traces(auto_id: str, _: str = Depends(require_admin)):
    _online()
    try:
        return {"traces": await automations.traces(auto_id)}
    except AutomationError as exc:
        _fail(exc)


@admin_routes.post("/api/home/automations/{entity_id}/toggle")
async def ha_automation_toggle(entity_id: str, request: Request, _: str = Depends(require_admin)):
    _online()
    try:
        await automations.toggle(entity_id, bool((await request.json()).get("on")))
    except AutomationError as exc:
        _fail(exc)
    return {"ok": True}


@admin_routes.post("/api/home/automations/{entity_id}/run")
async def ha_automation_run(entity_id: str, _: str = Depends(require_admin)):
    _online()
    try:
        await automations.run(entity_id)
    except AutomationError as exc:
        _fail(exc)
    return {"ok": True}


@admin_routes.post("/api/home/automations-draft")
async def ha_automation_draft(request: Request, _: str = Depends(require_admin)):
    _online()
    try:
        return await draft(home.brain, str((await request.json()).get("text", "")), automations.name)
    except AutomationError as exc:
        _fail(exc)
