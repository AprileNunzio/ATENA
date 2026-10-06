from fastapi import APIRouter, Depends

from access import require_admin
from features.understanding import claims, router

public_routes = APIRouter()
admin_routes = APIRouter()


@admin_routes.get("/api/understanding")
async def decisions(_: str = Depends(require_admin)):
    return {"enabled": router.enabled(), "reasoning": router.reasoning(), "domains": claims.DESCRIPTIONS, "decisions": router.recent()}
