import json
import os
import re
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from access import require_admin
from config import DEMO, STATE_DIR
from core_client import core
from features.chat import voice_id
from features.people import people
from features.vision.proxy import vision_proxy
from features.voices.catalog import VOICES
from state import store
from tasks import background

admin_routes = APIRouter()
FACES = Path(os.environ.get("ATENA_FACES_DIR", str(STATE_DIR / "faces")))


def is_scanned_unnamed(p: dict) -> bool:
    name = (p.get("name") or "").strip()
    slug = (p.get("slug") or "").strip()
    if slug.startswith("ospite-") or slug.startswith("sconosciut") or slug.startswith("guest-"):
        return True
    if re.match(r"^(ospite|sconosciuto|guest|unknown)(\s+\d+)?$", name, re.I):
        return True
    if p.get("auto") and (not p.get("first_name") or name.lower().startswith("ospite")):
        return True
    return False


def get_person_quality_pct(slug: str) -> int:
    clean = people.slugify(slug)
    d = FACES / clean
    if not d.is_dir():
        return 75
    meta_path = d / "meta.json"
    if meta_path.is_file():
        try:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            if "quality_pct" in m:
                return int(m["quality_pct"])
            samples = m.get("samples", 1)
            ir = m.get("samples_ir", 0)
            from features.vision.gallery import quality_percent
            return quality_percent(samples, ir)
        except Exception:
            pass
    return 75


async def sync_person_neuron(slug: str) -> None:
    p = people.get(slug)
    if not p:
        return
    props = {"role": p.get("role"), "preferences": p.get("preferences", {}),
             "habits": p["habits"]["summary"], "visits": p.get("stats", {}).get("visits", 0)}
    await core.remember(("node", {"id": f"person:{slug}", "node_type": "USER", "label": p["name"], "properties": props}))


@admin_routes.get("/api/people")
async def admin_people_list(_: str = Depends(require_admin)):
    plist = people.all_profiles()
    for p in plist:
        p["is_scanned"] = is_scanned_unnamed(p)
        p["quality_pct"] = get_person_quality_pct(p["slug"])
    return {"people": plist, "roles": people.ROLES, "voices": VOICES}


@admin_routes.get("/api/people/schema")
async def admin_people_schema(_: str = Depends(require_admin)):
    return {**people.schema(), "voices": VOICES}


@admin_routes.get("/api/people/reminders")
async def admin_reminders(days: int = 30, _: str = Depends(require_admin)):
    return {"reminders": people.reminders(max(1, min(days, 366)))}


@admin_routes.get("/api/people/{slug}")
async def admin_person(slug: str, _: str = Depends(require_admin)):
    p = people.get(slug)
    if not p:
        raise HTTPException(404, "Persona non trovata")
    p["sessions"] = p.get("sessions", [])[-50:]
    p["voiceprint"] = voice_id.status(slug)
    p["is_scanned"] = is_scanned_unnamed(p)
    p["quality_pct"] = get_person_quality_pct(slug)
    return p


@admin_routes.post("/api/people")
async def admin_person_create(request: Request, user: str = Depends(require_admin)):
    name = str((await request.json()).get("name", "")).strip()
    if not name or len(name) > 40:
        raise HTTPException(400, "Nome non valido")
    p = people.ensure(people.slugify(name), name)
    background(sync_person_neuron(p["slug"]))
    store.event("INFO", f"Profilo creato: {name} (da {user})", "people")
    return p


@admin_routes.put("/api/people/{slug}")
async def admin_person_update(slug: str, request: Request, _: str = Depends(require_admin)):
    changes = await request.json()
    try:
        p = people.update(slug, changes)
        if changes.get("name") and not DEMO:
            await vision_proxy(f"/people/{slug}", "PATCH", {"name": p["name"]})
    except KeyError:
        raise HTTPException(404, "Persona non trovata")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    background(sync_person_neuron(slug))
    return {"ok": True, "updated_at": p["updated_at"]}


@admin_routes.delete("/api/people/{slug}/voiceprint")
async def admin_person_voiceprint_delete(slug: str, user: str = Depends(require_admin)):
    if not people.load(slug):
        raise HTTPException(404, "Persona non trovata")
    voice_id.forget(slug)
    store.event("INFO", f"Impronta vocale cancellata: {slug} (da {user})", "people")
    return {"ok": True, "voiceprint": voice_id.status(slug)}


@admin_routes.delete("/api/people/{slug}")
async def admin_person_delete(slug: str, user: str = Depends(require_admin)):
    people.delete(slug)
    if not DEMO:
        await vision_proxy(f"/people/{slug}", "DELETE")
    store.event("INFO", f"Persona eliminata con tutti i dati: {slug} (da {user})", "people")
    return {"ok": True}


@admin_routes.post("/api/people/{from_slug}/associate")
async def admin_person_associate(from_slug: str, request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    to_slug = str(body.get("to_slug", "")).strip()
    if not to_slug:
        raise HTTPException(400, "Destinatario mancante")
    target = people.get(to_slug)
    if not target:
        raise HTTPException(404, "Persona di destinazione non trovata")

    clean_from = people.slugify(from_slug)
    clean_to = people.slugify(to_slug)
    src = FACES / clean_from
    dst = FACES / clean_to
    dst.mkdir(parents=True, exist_ok=True)
    dst_photos = dst / "photos"
    dst_photos.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        if (src / "photo.jpg").is_file():
            try:
                shutil.copy(src / "photo.jpg", dst_photos / f"scan_{int(time.time())}.jpg")
            except OSError:
                pass
        if (src / "photos").is_dir():
            for ph in (src / "photos").glob("*.jpg"):
                try:
                    shutil.copy(ph, dst_photos / f"merged_{ph.name}")
                except OSError:
                    pass
        try:
            import numpy as np
            if (src / "embeddings.npy").is_file() and (dst / "embeddings.npy").is_file():
                s_emb = np.load(src / "embeddings.npy")
                d_emb = np.load(dst / "embeddings.npy")
                merged = np.vstack([d_emb, s_emb])[:40]
                np.save(dst / "embeddings.npy", merged)
        except Exception:
            pass
        shutil.rmtree(src, ignore_errors=True)

    source_p = people.load(from_slug)
    if source_p:
        t_sessions = target.get("sessions", []) + source_p.get("sessions", [])
        target["sessions"] = sorted(t_sessions, key=lambda s: s[0])[-500:]
        target_stats = target.setdefault("stats", {"visits": 0, "total_seconds": 0})
        s_stats = source_p.get("stats", {})
        target_stats["visits"] = target_stats.get("visits", 0) + s_stats.get("visits", 0)
        target_stats["total_seconds"] = target_stats.get("total_seconds", 0) + s_stats.get("total_seconds", 0)
        people.save(target)

    people.delete(from_slug)
    from features.vision.nightly import optimize_person
    opt = optimize_person(clean_to)
    store.event("INFO", f"Volto scansionato {from_slug} associato a {target['name']} da {user}", "people")
    return {"ok": True, "target": people.get(to_slug), "optimization": opt}


@admin_routes.get("/api/people/{slug}/photos")
async def admin_person_photos(slug: str, _: str = Depends(require_admin)):
    clean = people.slugify(slug)
    d = FACES / clean
    if not d.is_dir():
        return {"photos": []}
    photos_dir = d / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    items = []
    primary = d / "photo.jpg"
    if primary.is_file():
        stat = primary.stat()
        items.append({
            "id": "photo_primary",
            "filename": "photo.jpg",
            "is_primary": True,
            "url": f"/api/vision/people/{clean}/photo.jpg",
            "created_at": stat.st_mtime,
            "quality_pct": get_person_quality_pct(clean),
        })
    for f in sorted(photos_dir.glob("*.jpg"), key=lambda p: -p.stat().st_mtime):
        stat = f.stat()
        items.append({
            "id": f.name,
            "filename": f.name,
            "is_primary": False,
            "url": f"/api/people/{clean}/photos/{f.name}",
            "created_at": stat.st_mtime,
            "quality_pct": get_person_quality_pct(clean),
        })
    return {"photos": items}


@admin_routes.get("/api/people/{slug}/photos/{photo_id}")
async def admin_person_photo_file(slug: str, photo_id: str, _: str = Depends(require_admin)):
    clean = people.slugify(slug)
    p_path = FACES / clean / "photos" / photo_id
    if p_path.is_file():
        return Response(p_path.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
    if photo_id in ("photo.jpg", "photo_primary") and (FACES / clean / "photo.jpg").is_file():
        return Response((FACES / clean / "photo.jpg").read_bytes(), media_type="image/jpeg")
    raise HTTPException(404, "Foto non trovata")


@admin_routes.delete("/api/people/{slug}/photos/{photo_id}")
async def admin_person_photo_delete(slug: str, photo_id: str, user: str = Depends(require_admin)):
    clean = people.slugify(slug)
    d = FACES / clean
    if not d.is_dir():
        raise HTTPException(404, "Persona non trovata")
    photos_dir = d / "photos"
    target = None
    if photo_id in ("photo_primary", "photo.jpg"):
        target = d / "photo.jpg"
    elif (photos_dir / photo_id).is_file():
        target = photos_dir / photo_id
    if not target or not target.is_file():
        raise HTTPException(404, "Foto non trovata")
    try:
        target.unlink()
    except OSError:
        pass

    if target.name == "photo.jpg":
        remaining = sorted(photos_dir.glob("*.jpg"), key=lambda p: -p.stat().st_mtime)
        if remaining:
            try:
                shutil.copy(remaining[0], d / "photo.jpg")
            except OSError:
                pass

    from features.vision.nightly import optimize_person
    opt = optimize_person(clean)
    store.event("INFO", f"Foto eliminata da galleria di {clean} da {user}", "vision")
    return {"ok": True, "optimization": opt}


@admin_routes.post("/api/people/{slug}/reproject")
async def admin_person_reproject(slug: str, user: str = Depends(require_admin)):
    clean = people.slugify(slug)
    from features.vision.nightly import optimize_person
    opt = optimize_person(clean)
    store.event("INFO", f"Riconoscimento riprogettato e ricalibrato per {clean} da {user}", "vision")
    return {"ok": True, "optimization": opt, "quality_pct": opt.get("quality_pct", 75)}


@admin_routes.post("/api/people/optimize-nightly")
async def admin_people_optimize_all(user: str = Depends(require_admin)):
    from features.vision.nightly import optimize_all
    res = optimize_all()
    store.event("INFO", f"Ottimizzazione notturna biometrica avviata manualmente da {user}", "vision")
    return res

