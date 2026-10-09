from fastapi import APIRouter, HTTPException, Request

from access import require_display
from features.ducking.ducker import ducker

public_routes = APIRouter()


@public_routes.post("/api/conversation/duck")
async def conversation_duck(request: Request):
    require_display(request, "Solo dal display")
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
        raise HTTPException(400, "Indica on: true o false")
    await ducker.signal(body["on"])
    return {"ok": True, "ducked": [t.name for t in ducker.ducked]}
