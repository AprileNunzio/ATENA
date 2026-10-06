from datetime import datetime

from fastapi import APIRouter, Depends

from access import require_admin
from loops import supervisor

admin_routes = APIRouter()


@admin_routes.get("/api/scheduler/state")
async def scheduler_state(_: str = Depends(require_admin)):
    from features.automations.engine import engine
    from features.automations.library import library
    return {"at": datetime.now().isoformat(timespec="seconds"), "totals": supervisor.totals(), "loops": supervisor.snapshot(),
            "upcoming": engine.scheduler.upcoming(list(library.items.values()))}
