from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin

from features.scene.graph import SceneError
from features.scene.service import scene

admin_routes = APIRouter()
public_routes = APIRouter()
KINDS = ("anchor", "item", "profile")


async def _body(request: Request) -> dict:
    if int(request.headers.get("content-length") or 0) > 16384:
        raise HTTPException(413, "scene.error.too_large")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "scene.error.body")
    return body


@admin_routes.get("/api/scene")
async def scene_overview(_: str = Depends(require_admin)):
    g = scene.graph
    items = [{**i, "seen": g.last_seen(i["labels"])} for i in g.items()]
    return {"anchors": g.anchors(), "items": items, "profiles": [{**p, "status": g.readiness(p)} for p in g.profiles()],
            "fusion": scene.fusion.step(), "graph": g.export(), "labels": _labels()}


def _labels() -> list[str]:
    try:
        from features.vision.objects import LABELS_IT, SCENERY
    except Exception:
        return []
    return [label for label in LABELS_IT if label not in SCENERY]


@admin_routes.post("/api/scene/{kind}")
async def scene_save(kind: str, request: Request, _: str = Depends(require_admin)):
    if kind not in KINDS:
        raise HTTPException(404, "scene.error.kind")
    body = await _body(request)
    try:
        return getattr(scene.graph, f"save_{kind}")(body)
    except SceneError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.delete("/api/scene/{kind}/{entry_id}")
async def scene_delete(kind: str, entry_id: str, _: str = Depends(require_admin)):
    try:
        if not scene.graph.delete(kind, entry_id):
            raise HTTPException(404, "scene.error.missing")
    except SceneError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}
