from fastapi import APIRouter, Depends, HTTPException

from access import require_admin
from features.team import roster

public_routes = APIRouter()
admin_routes = APIRouter()


@admin_routes.get("/api/team")
async def team(_: str = Depends(require_admin)):
    return roster.document()


@admin_routes.get("/api/team/{agent_id}")
async def member(agent_id: str, _: str = Depends(require_admin)):
    try:
        return roster.profile(roster.find(agent_id))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
