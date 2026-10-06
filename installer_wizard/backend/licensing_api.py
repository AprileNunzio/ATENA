from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

import licensing
from access import NO_CACHE, require_admin
from config import ATENA_DIR

admin_routes = APIRouter()
NOTICES = ATENA_DIR / "THIRD_PARTY_NOTICES.md"
MAX_NOTICES = 256 * 1024


@admin_routes.get("/api/licenses")
async def licenses(_: str = Depends(require_admin)):
    text = NOTICES.read_text(encoding="utf-8")[:MAX_NOTICES] if NOTICES.is_file() else ""
    return JSONResponse({**licensing.status(), "notices": text}, headers=NO_CACHE)
