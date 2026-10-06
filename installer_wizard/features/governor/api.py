from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin, require_display
from features.governor.devices import ID_RE, clean_report
from features.governor.service import governor

public_routes = APIRouter()
admin_routes = APIRouter()
MAX_BODY = 32768


@public_routes.get("/api/governor/policy")
async def policy(request: Request, device: str = ""):
    require_display(request, "Solo dal display")
    return governor.policy(device if ID_RE.match(device) else None)


@public_routes.post("/api/governor/report")
async def report(request: Request):
    require_display(request, "Solo dal display")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Rapporto troppo grande")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Rapporto non valido") from None
    clean = clean_report(body)
    if clean is None:
        raise HTTPException(400, "Rapporto non valido")
    return governor.report(clean)


@admin_routes.get("/api/governor/state")
async def state(minutes: int = 60, _: str = Depends(require_admin)):
    return governor.state(max(5, min(1440, minutes)))


@admin_routes.get("/api/governor/history")
async def history(minutes: int = 120, _: str = Depends(require_admin)):
    return {"samples": governor.ledger.history(max(5, min(10080, minutes)))}


@admin_routes.get("/api/governor/estimate")
async def estimate(component: str, size: float = 0.0, _: str = Depends(require_admin)):
    return governor.ledger.estimate(component[:80], None, max(0.0, size)) or {}


@admin_routes.post("/api/governor/reset")
async def reset(_: str = Depends(require_admin)):
    governor.ledger.clear()
    return {"ok": True}


@admin_routes.post("/api/governor/devices/forget")
async def forget(_: str = Depends(require_admin)):
    governor.devices.forget()
    return {"ok": True}
