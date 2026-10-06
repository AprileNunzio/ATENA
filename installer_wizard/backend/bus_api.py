import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from access import NO_CACHE, require_admin, require_display
from atena_bus import Envelope, atena_bus, valid_pattern

admin_routes = APIRouter()
public_routes = APIRouter()
QUEUE_SIZE = 256
MAX_PATTERNS = 16
KEEPALIVE = 15.0
DISPLAY_PREFIXES = ("ui.", "nvr.status", "nvr.event.", "system.module.")


def _patterns(raw: str, display: bool) -> list[str]:
    patterns = [p.strip() for p in raw.split(",") if p.strip()][:MAX_PATTERNS]
    if not patterns or not all(valid_pattern(p) for p in patterns):
        raise HTTPException(400, "bus.error.pattern")
    if display and not all(p.startswith(DISPLAY_PREFIXES) for p in patterns):
        raise HTTPException(403, "bus.error.forbidden")
    return patterns


def stream(patterns: list[str]):
    async def generator(request: Request):
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(QUEUE_SIZE)

        def push(envelope: Envelope) -> None:
            def put() -> None:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(envelope)
            loop.call_soon_threadsafe(put)

        subs = [atena_bus.subscribe(p, push, replay=True) for p in patterns]
        try:
            while not await request.is_disconnected():
                try:
                    envelope = await asyncio.wait_for(queue.get(), KEEPALIVE)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(envelope.to_dict(), ensure_ascii=False, default=str)}\n\n"
        finally:
            for sub in subs:
                sub.cancel()
    return generator


@admin_routes.get("/api/bus/stream")
async def admin_stream(request: Request, topics: str = "", _: str = Depends(require_admin)):
    return StreamingResponse(stream(_patterns(topics, False))(request), media_type="text/event-stream",
                             headers={**NO_CACHE, "X-Accel-Buffering": "no"})


@public_routes.get("/api/bus/stream")
async def display_stream(request: Request, topics: str = ""):
    require_display(request)
    return StreamingResponse(stream(_patterns(topics, True))(request), media_type="text/event-stream",
                             headers={**NO_CACHE, "X-Accel-Buffering": "no"})


@admin_routes.get("/api/bus/modules")
async def bus_modules(_: str = Depends(require_admin)):
    return {"modules": atena_bus.modules(), "stats": atena_bus.stats()}
