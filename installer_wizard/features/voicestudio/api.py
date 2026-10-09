import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from access import NO_CACHE, require_admin
from config import env_get, write_env
from features.voices import catalog
from features.voicestudio import design
from features.voicestudio.client import MAX_AUDIO, StudioError, client, voice_id
from state import store
from tasks import background

admin_routes = APIRouter()
NAME_RE = re.compile(r"^[\w àèéìòùÀÈÉÌÒÙ'.-]{1,40}$")
AUDIO_TYPES = ("audio/", "video/webm", "application/octet-stream")


def _name(raw: str) -> str:
    name = " ".join(str(raw or "").split())
    if not NAME_RE.match(name):
        raise HTTPException(400, "Dai alla voce un nome breve (lettere e numeri)")
    return name


def _fail(exc: StudioError) -> HTTPException:
    return HTTPException(502, str(exc))


def _step() -> dict:
    rec = store.steps.get("voicestudio") or {}
    return {k: rec.get(k) for k in ("status", "progress", "message", "error")}


@admin_routes.get("/api/voicestudio")
async def studio_status(_: str = Depends(require_admin)):
    out = {"enabled": client.enabled(), "where": "remote" if client.remote() else "local",
           "url": env_get("ATENA_VOICESTUDIO_URL", ""), "has_key": bool(env_get("ATENA_VOICESTUDIO_KEY", "")),
           "install": _step(), "online": False, "error": "", "voices": [], "atena_voice": catalog.voice_name(),
           "sentences": design.SENTENCES, "choices": design.CHOICES}
    if out["enabled"]:
        try:
            out["voices"] = await client.voices(fresh=True)
            out["online"] = True
        except StudioError as exc:
            out["error"] = str(exc)
    return out


@admin_routes.post("/api/voicestudio/check")
async def studio_check(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    key = str(body.get("key") or "").strip() or None
    try:
        return await client.check(str(body.get("url") or "") or None, key)
    except StudioError as exc:
        return {"ok": False, "message": str(exc)}


@admin_routes.post("/api/voicestudio/retry")
async def studio_retry(user: str = Depends(require_admin)):
    if not client.enabled() or client.remote():
        raise HTTPException(409, "Lo Studio locale non è acceso")
    from orchestrator import converge_steps
    background(converge_steps(["voicestudio"], f"Nuovo tentativo dello Studio delle voci ({user})"))
    return {"ok": True}


@admin_routes.post("/api/voicestudio/design")
async def studio_design(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    name = _name(body.get("name"))
    try:
        description = design.describe(body)
        profile = await client.design(name, description, design.language(body.get("language")))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except StudioError as exc:
        raise _fail(exc)
    store.event("INFO", f"Nuova voce inventata nello Studio: {name} ({user})", "voice")
    return {"ok": True, "voice": voice_id(profile["id"])}


@admin_routes.post("/api/voicestudio/clone")
async def studio_clone(name: str = Form(...), language: str = Form("it"), consent: str = Form(""),
                       audio: UploadFile = File(...), user: str = Depends(require_admin)):
    name = _name(name)
    if consent != "1":
        raise HTTPException(400, "Serve il consenso della persona di cui copi la voce")
    if not str(audio.content_type or "").startswith(AUDIO_TYPES):
        raise HTTPException(400, "Il file non è una registrazione audio")
    data = await audio.read(MAX_AUDIO + 1)
    if len(data) < 20_000 or len(data) > MAX_AUDIO:
        raise HTTPException(400, "Registrazione troppo corta o troppo lunga: leggi tutta la frase")
    lang = design.language(language)
    try:
        profile = await client.clone(name, data, design.filename(audio.filename), design.sentence(lang, name), lang)
    except StudioError as exc:
        raise _fail(exc)
    store.event("INFO", f"Voce copiata nello Studio con consenso registrato: {name} ({user})", "voice")
    return {"ok": True, "voice": voice_id(str(profile.get("id", "")))}


@admin_routes.post("/api/voicestudio/preview")
async def studio_preview(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    lang = design.language(body.get("language"))
    text = str(body.get("text") or design.PREVIEW.get(lang, design.PREVIEW["it"]))[:300]
    try:
        wav = await client.speech(text, str(body.get("voice") or ""), 1.0, lang)
    except StudioError as exc:
        raise _fail(exc)
    return Response(wav, media_type="audio/wav", headers=NO_CACHE)


@admin_routes.put("/api/voicestudio/use")
async def studio_use(request: Request, user: str = Depends(require_admin)):
    voice = str((await request.json()).get("voice") or "")
    known = {v["id"] for v in await _voices()}
    if voice and voice not in known:
        raise HTTPException(404, "Voce non trovata nello Studio")
    rest = [v for v in catalog.custom_order() or [catalog.voice_name()] if not catalog.is_studio(v)]
    order = ([voice] if voice else []) + rest
    write_env({"ATENA_VOICE_ORDER": ",".join(dict.fromkeys(order)), "ATENA_VOICE": order[0]})
    store.event("INFO", f"Voce di Atena: {client.name_of(voice) if voice else order[0]} ({user})", "voice")
    return {"ok": True, "atena_voice": order[0]}


@admin_routes.delete("/api/voicestudio/voices/{voice}")
async def studio_delete(voice: str, user: str = Depends(require_admin)):
    if voice in catalog.custom_order():
        _drop(voice)
    try:
        await client.delete(voice)
    except StudioError as exc:
        raise _fail(exc)
    store.event("INFO", f"Voce eliminata dallo Studio: {voice} ({user})", "voice")
    return {"ok": True}


def _drop(voice: str) -> None:
    rest = [v for v in catalog.custom_order() if v != voice]
    write_env({"ATENA_VOICE_ORDER": ",".join(rest), "ATENA_VOICE": rest[0] if rest else ""})


async def _voices() -> list[dict]:
    try:
        return await client.voices(fresh=True)
    except StudioError as exc:
        raise _fail(exc)
