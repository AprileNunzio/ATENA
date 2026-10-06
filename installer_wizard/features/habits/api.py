from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin
from features.habits.foresight import foresight
from features.habits.service import enabled, habits, threshold

public_routes = APIRouter()
admin_routes = APIRouter()


@admin_routes.get("/api/habits")
async def overview(_: str = Depends(require_admin)):
    items = sorted(habits.data["suggestions"].values(), key=lambda s: (s["status"] != "new", -s["confidence"]))
    return {"enabled": enabled(), "threshold": threshold(), "events": habits.journal.count(), "mined": habits.data.get("mined", 0),
            "asking": habits.waiting(), "suggestions": items, "anomalies": habits.data.get("anomalies", [])[:20],
            "foresight": foresight.listing(), "foresight_hits": foresight.hits}


@admin_routes.post("/api/habits/analyse")
async def analyse(_: str = Depends(require_admin)):
    import asyncio
    found = await asyncio.to_thread(habits.analyse)
    return {"found": len(found)}


@admin_routes.post("/api/habits/{sid}")
async def decide(sid: str, request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    verdict = str(body.get("verdict") or "")
    if verdict not in ("accept", "reject", "snooze"):
        raise HTTPException(400, "Decisione non valida")
    if sid not in habits.data["suggestions"]:
        raise HTTPException(404, "Proposta sconosciuta")
    return {"message": habits.decide(sid, verdict)}


@admin_routes.get("/api/habits/feedback")
async def feedback_listing(_: str = Depends(require_admin)):
    from features.habits.feedback import feedback
    return {"items": feedback.listing(), "pending": len(feedback.pending)}


@admin_routes.delete("/api/habits/feedback")
async def feedback_reset(key: str = "", _: str = Depends(require_admin)):
    from features.habits.feedback import feedback
    return {"removed": feedback.reset(key[:400])}
