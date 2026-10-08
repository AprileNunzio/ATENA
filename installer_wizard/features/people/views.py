import logging
import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from access import NO_CACHE, require_admin
from config import STATE_DIR
from features.people import people
from features.vision.proxy import VISION_URL
from state import store

log = logging.getLogger("atena.people")
admin_routes = APIRouter()
FACES = Path(os.environ.get("ATENA_FACES_DIR", str(STATE_DIR / "faces")))
KINDS = ("front", "three_left", "three_right", "left", "right", "up", "down", "body", "body_back")
BODY = ("body", "body_back")
PHOTO_ID = re.compile(r"^(photo_primary|[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.jpg)$")
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/bmp")
MAX_BYTES = 8 * 1024 * 1024


def kind_of(filename: str) -> str:
    head = filename.rsplit("_", 1)[0]
    return head if head in KINDS else "sample"


def check_photo_id(photo_id: str) -> None:
    if not PHOTO_ID.match(photo_id) or ".." in photo_id:
        raise HTTPException(400, "Nome della foto non valido")


def coverage(slug: str) -> dict:
    folder = FACES / people.slugify(slug) / "photos"
    counts: dict[str, int] = {}
    if folder.is_dir():
        for f in folder.glob("*.jpg"):
            kind = kind_of(f.stem)
            if kind in KINDS:
                counts[kind] = counts.get(kind, 0) + 1
    if (FACES / people.slugify(slug) / "photo.jpg").is_file():
        counts["front"] = counts.get("front", 0) + 1
    return counts


def _person(slug: str) -> dict:
    p = people.load(slug)
    if not p:
        raise HTTPException(404, "Persona non trovata")
    return p


def _kind(request: Request, allow_auto: bool) -> str:
    kind = str(request.query_params.get("kind", "auto" if allow_auto else ""))
    if kind not in KINDS and not (allow_auto and kind == "auto"):
        raise HTTPException(400, "Tipo di vista non valido")
    return kind


async def _forward(path: str, params: dict, content: bytes | None, timeout: float) -> Response:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{VISION_URL}{path}", params=params, content=content,
                                  headers={"Content-Type": "application/octet-stream"} if content else None)
    except httpx.HTTPError:
        raise HTTPException(503, "Servizio di visione non disponibile")
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"), headers=NO_CACHE)


@admin_routes.get("/api/people/{slug}/views")
async def person_views(slug: str, _: str = Depends(require_admin)):
    _person(slug)
    return {"kinds": list(KINDS), "views": coverage(slug)}


@admin_routes.post("/api/people/{slug}/views")
async def upload_view(slug: str, request: Request, user: str = Depends(require_admin)):
    p = _person(slug)
    kind = _kind(request, True)
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype not in IMAGE_TYPES:
        raise HTTPException(415, "Carica una foto JPEG, PNG, WEBP o BMP")
    length = int(request.headers.get("content-length") or 0)
    if length > MAX_BYTES:
        raise HTTPException(413, "Foto più grande di 8 MB")
    data = await request.body()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "Foto vuota o più grande di 8 MB")
    resp = await _forward(f"/people/{people.slugify(slug)}/views", {"kind": kind, "name": p["name"]}, data, 60)
    if resp.status_code == 200:
        store.event("INFO", f"Foto ({kind}) aggiunta alla galleria di {p['name']} da {user}", "people")
    return resp


@admin_routes.post("/api/people/{slug}/views/capture")
async def capture_view(slug: str, request: Request, user: str = Depends(require_admin)):
    p = _person(slug)
    kind = _kind(request, False)
    resp = await _forward(f"/people/{people.slugify(slug)}/views/capture", {"kind": kind, "name": p["name"]}, None, 30)
    if resp.status_code == 200:
        store.event("INFO", f"Vista {kind} acquisita dalla webcam per {p['name']} da {user}", "people")
    return resp
