import json
import logging
from pathlib import Path

import httpx
from fastapi import HTTPException

from features.people import people
from features.vision.proxy import VISION_URL, vision_proxy

log = logging.getLogger("atena.people")
GOOD_SAMPLES = 20


def _meta(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("Metadati del volto %s illeggibili: %s", folder.name, exc)
        return None
    return data if isinstance(data, dict) else None


def _adopt(entries: list[tuple[str, dict]]) -> list[str]:
    created = []
    for slug, meta in entries:
        slug = people.slugify(slug)
        if people.load(slug) is not None:
            continue
        profile = people.ensure(slug, str(meta.get("name") or slug)[:40])
        profile["auto"] = bool(meta.get("auto"))
        people.save(profile)
        created.append(slug)
    if created:
        log.info("Volti della galleria aggiunti a Persone: %s", ", ".join(created))
    return created


def sync_gallery(faces: Path) -> list[str]:
    if not faces.is_dir():
        return []
    folders = sorted(p for p in faces.iterdir() if p.is_dir())
    return _adopt([(f.name, meta) for f in folders if (meta := _meta(f)) is not None])


def sync_listing(listing: list) -> list[str]:
    rows = [p for p in listing if isinstance(p, dict) and isinstance(p.get("slug"), str) and p["slug"].strip()]
    return _adopt([(p["slug"], p) for p in rows])


async def sync_vision() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VISION_URL}/people")
        r.raise_for_status()
        listing = r.json().get("people", [])
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        log.info("Elenco volti dal servizio di visione non disponibile: %s", exc)
        return []
    return sync_listing(listing if isinstance(listing, list) else [])


def quality(faces: Path, slug: str) -> int:
    folder = faces / people.slugify(slug)
    meta = _meta(folder)
    if meta is None or not (folder / "embeddings.npy").is_file():
        return 0
    if "quality_pct" in meta:
        return int(meta["quality_pct"])
    from features.vision.gallery import quality_percent
    return quality_percent(int(meta.get("samples", 1)), int(meta.get("samples_ir", 0)))


async def associate(from_slug: str, to_slug: str) -> dict:
    target = people.load(to_slug)
    if not target:
        raise HTTPException(404, "Persona di destinazione non trovata")
    if people.slugify(from_slug) == people.slugify(to_slug):
        raise HTTPException(400, "Un volto non può essere associato a se stesso")
    resp = await vision_proxy(f"/people/{people.slugify(from_slug)}/merge", "POST",
                              {"into": people.slugify(to_slug), "name": target["name"]}, timeout=60)
    if resp.status_code not in (200, 404):
        detail = json.loads(resp.body or b"{}").get("detail") or "Unione dei volti non riuscita"
        raise HTTPException(resp.status_code, detail)
    source = people.load(from_slug)
    if source:
        sessions = target.get("sessions", []) + source.get("sessions", [])
        target["sessions"] = sorted(sessions, key=lambda s: s[0])[-500:]
        stats = target.setdefault("stats", {"visits": 0, "total_seconds": 0})
        for key in ("visits", "total_seconds"):
            stats[key] = stats.get(key, 0) + source.get("stats", {}).get(key, 0)
        people.save(target)
        people.delete(from_slug)
    return people.get(to_slug)
