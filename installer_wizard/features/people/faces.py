import json
import logging
from pathlib import Path

from fastapi import HTTPException

from features.people import people
from features.vision.proxy import vision_proxy

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


def sync_gallery(faces: Path) -> list[str]:
    if not faces.is_dir():
        return []
    created = []
    for folder in sorted(p for p in faces.iterdir() if p.is_dir()):
        meta = _meta(folder)
        if meta is None or people.load(folder.name) is not None:
            continue
        profile = people.ensure(folder.name, str(meta.get("name") or folder.name))
        profile["auto"] = bool(meta.get("auto"))
        people.save(profile)
        created.append(folder.name)
    if created:
        log.info("Volti della galleria aggiunti a Persone: %s", ", ".join(created))
    return created


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
    target = people.get(to_slug)
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
