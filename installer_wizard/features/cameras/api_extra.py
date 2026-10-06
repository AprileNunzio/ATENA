from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from access import require_admin
from state import store

from features.cameras import captures, controls, discovery, events, options, presets, probe, unified
from features.cameras.api_shared import source_of

router = APIRouter()


def guard(call):
    try:
        return call()
    except KeyError:
        raise HTTPException(404, "Elemento non trovato")
    except FileNotFoundError:
        raise HTTPException(404, "File non trovato")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/api/cameras/overview")
async def overview(_: str = Depends(require_admin)):
    return unified.overview()


@router.get("/api/cameras/presets")
async def preset_list(_: str = Depends(require_admin)):
    return {"brands": presets.listing()}


@router.post("/api/cameras/presets/build")
async def preset_build(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    url = guard(lambda: presets.build(str(body.get("brand", "")), str(body.get("host", "")).strip(), str(body.get("user", "")),
                                      str(body.get("password", "")), body.get("channel", 1), str(body.get("stream", "main")), body.get("port", 0)))
    return {"url": url}


@router.post("/api/cameras/discover")
async def discover(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    if body.get("confirm") is not True:
        raise HTTPException(400, "Serve la conferma esplicita: la ricerca contatta gli indirizzi della rete locale")
    try:
        result = await discovery.find(str(body.get("network", "")).strip())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    store.event("INFO", f"Ricerca telecamere in rete avviata da {user}: {len(result['found'])} trovate", "cameras")
    return result


@router.post("/api/cameras/probe")
async def test_url(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    return await probe.test(str(body.get("url", "")).strip())


@router.get("/api/cameras/events")
async def event_list(source: str = "", _: str = Depends(require_admin)):
    return {"events": events.recent(100, source if options.SOURCE_RE.match(source) else "")}


@router.delete("/api/cameras/events")
async def event_clear(_: str = Depends(require_admin)):
    events.clear()
    return {"ok": True}


@router.put("/api/cameras/source/{source_id}/options")
async def put_options(source_id: str, request: Request, _: str = Depends(require_admin)):
    source_of(source_id)
    body = await request.json()
    body.pop("controls", None)
    return guard(lambda: options.put(source_id, body))


@router.put("/api/cameras/source/{source_id}/record")
async def put_record(source_id: str, request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    result = guard(lambda: unified.set_record(source_id, body))
    store.event("INFO", f"Registrazione di {source_id} aggiornata da {user}", "cameras")
    return result


@router.delete("/api/cameras/source/{source_id}")
async def forget_source(source_id: str, user: str = Depends(require_admin)):
    removed = guard(lambda: unified.remove(source_id))
    store.event("INFO", f"Sorgente {source_id} rimossa da {user} ({removed['photos']} foto, {removed['clips']} clip)", "cameras")
    return removed


@router.get("/api/cameras/source/{source_id}/controls")
async def get_controls(source_id: str, _: str = Depends(require_admin)):
    node = guard(lambda: controls.node_of(source_of(source_id)))
    try:
        return {"controls": controls.read(node), "saved": options.get(source_id)["controls"]}
    except (OSError, FileNotFoundError) as exc:
        raise HTTPException(503, str(exc))


@router.put("/api/cameras/source/{source_id}/controls")
async def set_control(source_id: str, request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    node = guard(lambda: controls.node_of(source_of(source_id)))
    name, value = str(body.get("name", "")), body.get("value")
    row = guard(lambda: controls.apply(node, name, value))
    saved = dict(options.get(source_id)["controls"])
    saved[name] = value
    options.put(source_id, {"controls": saved})
    return row


@router.post("/api/cameras/source/{source_id}/controls/reset")
async def reset_controls(source_id: str, _: str = Depends(require_admin)):
    node = guard(lambda: controls.node_of(source_of(source_id)))
    count = guard(lambda: controls.reset(node))
    options.put(source_id, {"controls": {}})
    return {"reset": count}


@router.post("/api/cameras/source/{source_id}/photo")
async def take_photo(source_id: str, user: str = Depends(require_admin)):
    try:
        photo = await captures.take(source_of(source_id))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    store.event("INFO", f"Foto scattata da {user}: {source_id}", "cameras")
    return photo


@router.get("/api/cameras/source/{source_id}/photos")
async def list_photos(source_id: str, _: str = Depends(require_admin)):
    source_of(source_id)
    return {"photos": guard(lambda: captures.photos(source_id))}


@router.get("/api/cameras/source/{source_id}/photos/{name}")
async def get_photo(source_id: str, name: str, _: str = Depends(require_admin)):
    path = guard(lambda: captures.photo_path(source_id, name))
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/api/cameras/source/{source_id}/photos/{name}")
async def remove_photo(source_id: str, name: str, _: str = Depends(require_admin)):
    guard(lambda: captures.delete_photo(source_id, name))
    return {"ok": True}


@router.get("/api/cameras/clips/{registry_id}")
async def list_clips(registry_id: str, _: str = Depends(require_admin)):
    return {"clips": guard(lambda: captures.clips(registry_id))}


@router.get("/api/cameras/clips/{registry_id}/{name}")
async def get_clip(registry_id: str, name: str, _: str = Depends(require_admin)):
    path = guard(lambda: captures.clip_path(registry_id, name))
    return FileResponse(path, media_type="video/mp4", filename=name, headers={"Cache-Control": "private, no-store"})


@router.delete("/api/cameras/clips/{registry_id}/{name}")
async def remove_clip(registry_id: str, name: str, _: str = Depends(require_admin)):
    guard(lambda: captures.clip_path(registry_id, name).unlink())
    return {"ok": True}
