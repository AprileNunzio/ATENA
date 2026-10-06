import asyncio
import logging
import re
import time
from pathlib import Path

from features.music import cast_chrome, catalog, conf, dlna, layout, listening, mixes, tokens
from features.music.db import db
from state import store

log = logging.getLogger("atena.music")
DEVICE_RE = re.compile(r"^(cast|dlna|display):[A-Za-z0-9._-]{1,64}$")
KNOWN_TTL = 600.0
DISCOVER_TTL = 90.0
POLL_PERIOD = 4.0
END_GRACE = 6.0
REPEAT = ("off", "all", "one")
REMOTE_WAIT = 25.0
MAX_QUEUE = 1000


class Session:

    def __init__(self, device_id: str, user: str) -> None:
        self.device_id = device_id
        self.user = user
        self.queue: list[int] = []
        self.index = 0
        self.state = "stopped"
        self.base = 0.0
        self.since = time.time()
        self.duration = 0.0
        self.volume = 0.6
        self.repeat = "off"
        self.loaded_at = 0.0
        self.error = ""
        self.counted = False
        self.seed: int | None = None
        self.base_url = ""

    def position(self) -> float:
        if self.state == "playing":
            return min(self.duration or 1e9, self.base + time.time() - self.since)
        return self.base

    def anchor(self, position: float, state: str) -> None:
        self.base, self.since, self.state = max(0.0, position), time.time(), state

    @property
    def current(self) -> int | None:
        return self.queue[self.index] if 0 <= self.index < len(self.queue) else None


class Outputs:

    def __init__(self) -> None:
        self.devices: dict[str, dict] = {}
        self.sessions: dict[str, Session] = {}
        self.discovered = 0.0
        self.remote_queue: dict[str, asyncio.Queue] = {}
        self.lock = asyncio.Lock()

    def remote_beat(self, device_id: str, name: str) -> None:
        self.devices[device_id] = {"id": device_id, "kind": "display", "name": name[:40] or "Schermo Atena", "seen": time.time()}
        self.remote_queue.setdefault(device_id, asyncio.Queue())

    async def wait_command(self, device_id: str, name: str) -> dict | None:
        self.remote_beat(device_id, name)
        try:
            return await asyncio.wait_for(self.remote_queue[device_id].get(), REMOTE_WAIT)
        except asyncio.TimeoutError:
            self.remote_beat(device_id, name)
            return None

    async def refresh(self, force: bool = False) -> list[dict]:
        if conf.cast_enabled() and (force or time.time() - self.discovered > DISCOVER_TTL):
            self.discovered = time.time()
            found = await asyncio.gather(dlna.discover(), self.safe_cast(), return_exceptions=True)
            for batch in found:
                if isinstance(batch, Exception):
                    log.info("Ricerca dispositivi: %s", batch)
                    continue
                for device in batch:
                    self.devices[device["id"]] = {**device, "seen": time.time()}
        cutoff = time.time() - KNOWN_TTL
        for key in [k for k, d in self.devices.items() if d.get("seen", 0) < cutoff]:
            self.devices.pop(key)
            self.remote_queue.pop(key, None)
        return self.listing()

    @staticmethod
    async def safe_cast() -> list[dict]:
        try:
            return await cast_chrome.discover()
        except RuntimeError as exc:
            log.info("Chromecast non cercati: %s", exc)
            return []

    def listing(self) -> list[dict]:
        rows = []
        for device in self.devices.values():
            session = self.sessions.get(device["id"])
            rows.append({"id": device["id"], "kind": device["kind"], "name": device["name"], "model": device.get("model", ""),
                         "active": bool(session and session.state in ("playing", "paused", "loading"))})
        return sorted(rows, key=lambda r: (r["kind"], r["name"].lower()))

    def device(self, device_id: str) -> dict:
        if not DEVICE_RE.match(device_id) or device_id not in self.devices:
            raise KeyError("Dispositivo non trovato")
        return self.devices[device_id]

    def urls(self, track: dict, base: str) -> tuple[str, str]:
        token = tokens.sign("media", track["id"], max(6 * 3600, track["duration"] * 2 + 600))
        art = tokens.sign("art", track["album_key"], 12 * 3600)
        return f"{base}/api/music/media/{track['id']}?t={token}", f"{base}/api/music/art/{track['album_key']}?t={art}&size=600"

    def meta(self, track: dict, base: str) -> tuple[str, dict]:
        row = db.row("SELECT path FROM tracks WHERE id=?", (track["id"],)) or {"path": ""}
        url, art = self.urls(track, base)
        suffix = Path(row["path"]).suffix.lower()
        mode = conf.transcode_mode()
        if mode == "always" or (mode == "auto" and suffix not in layout.BROWSER_SAFE):
            url, mime = f"{url}&fmt=mp3", "audio/mpeg"
        else:
            mime = layout.mime(row["path"])
        return url, {"title": track["title"], "artist": track["artist"], "album": track["album"], "art": art if track["cover"] else "", "mime": mime}

    async def start(self, device_id: str, user: str, ids: list[int], index: int, start: float, base: str, repeat: str = "off") -> dict:
        self.device(device_id)
        queue = [t["id"] for t in catalog.by_ids(ids[:MAX_QUEUE])]
        if not queue:
            raise ValueError("Nessun brano da riprodurre")
        session = self.sessions.get(device_id) or Session(device_id, user)
        session.user, session.queue, session.repeat, session.base_url = user, queue, repeat if repeat in REPEAT else "off", base
        session.index = max(0, min(len(queue) - 1, int(index)))
        session.seed = None
        self.sessions[device_id] = session
        await self.load(session, base, float(start or 0))
        return self.view(session)

    async def load(self, session: Session, base: str, start: float = 0.0) -> None:
        track = catalog.track(session.current) if session.current is not None else None
        if not track:
            session.anchor(0, "stopped")
            return
        device = self.device(session.device_id)
        url, meta = self.meta(track, base)
        session.error = ""
        session.duration = float(track["duration"] or 0)
        session.counted = False
        session.loaded_at = time.time()
        try:
            if device["kind"] == "dlna":
                await dlna.load(device, url, meta)
                if start > 1:
                    await dlna.control(device, "seek", start)
            elif device["kind"] == "cast":
                await cast_chrome.load(device, url, meta, start)
            else:
                await self.remote_queue[session.device_id].put({"type": "load", "url": url, "start": start, "meta": meta,
                                                               "volume": session.volume, "id": track["id"]})
        except RuntimeError as exc:
            session.error = str(exc)
            session.anchor(0, "stopped")
            raise
        session.anchor(start, "playing")
        self.announce(track, session)

    def announce(self, track: dict, session: Session) -> None:
        now = time.time()
        store.now_playing = {"title": track["title"], "artist": track["artist"], "album": track["album"], "year": track["year"] or None,
                             "genre": track["genre"] or None, "duration": track["duration"] or None, "key": f"lib:{track['id']}",
                             "cover": f"/api/music/art/{track['album_key']}?t={tokens.sign('art', track['album_key'], 12 * 3600)}&size=300" if track["cover"] else None,
                             "started_at": now - session.base, "recognized_at": now, "expires": now + (track["duration"] or 240) + 45,
                             "source": "library", "device": session.device_id}
        store.touch()

    def clear_announcement(self, session: Session) -> None:
        current = store.now_playing or {}
        if current.get("source") == "library" and current.get("device") == session.device_id:
            store.now_playing = {}
            store.touch()

    async def control(self, device_id: str, action: str, value: float = 0.0, base_url: str = "") -> dict:
        device = self.device(device_id)
        session = self.sessions.get(device_id)
        if session is None:
            raise ValueError("Nessuna riproduzione su questo dispositivo")
        base = session.base_url or base_url
        if action in ("next", "prev"):
            return await self.step(session, base, 1 if action == "next" else -1)
        if action == "repeat":
            session.repeat = REPEAT[(REPEAT.index(session.repeat) + 1) % 3]
            return self.view(session)
        await self.apply(device, session, action, value)
        return self.view(session)

    async def apply(self, device: dict, session: Session, action: str, value: float) -> None:
        if action not in ("pause", "resume", "stop", "seek", "volume"):
            raise ValueError("Comando non valido")
        if device["kind"] == "dlna":
            await dlna.control(device, action, value)
        elif device["kind"] == "cast":
            await cast_chrome.control(device, action, value)
        else:
            await self.remote_queue[session.device_id].put({"type": action, "value": value})
        if action == "pause":
            session.anchor(session.position(), "paused")
        elif action == "resume":
            session.anchor(session.base, "playing")
        elif action == "seek":
            session.anchor(value, session.state if session.state != "stopped" else "playing")
        elif action == "volume":
            session.volume = max(0.0, min(1.0, float(value)))
        else:
            self.finish(session)

    def finish(self, session: Session) -> None:
        self.record(session, False)
        session.anchor(0, "stopped")
        self.clear_announcement(session)

    def record(self, session: Session, done: bool) -> None:
        if session.counted or session.current is None:
            return
        session.counted = True
        listening.played(session.user, session.current, session.position() if not done else session.duration, done, "uscita")

    async def step(self, session: Session, base: str, direction: int, ended: bool = False) -> dict:
        self.record(session, ended)
        index = session.index + direction
        if session.repeat == "one" and ended:
            index = session.index
        elif index >= len(session.queue):
            if session.repeat == "all":
                index = 0
            elif conf.radio() and session.queue:
                await self.extend(session)
                index = session.index + 1
        elif index < 0:
            index = 0
        if not 0 <= index < len(session.queue):
            self.finish(session)
            return self.view(session)
        session.index = index
        await self.load(session, base)
        return self.view(session)

    async def extend(self, session: Session) -> None:
        seed = session.seed or session.queue[-1]
        more = await asyncio.to_thread(mixes.similar, seed, session.user, session.queue, 12)
        session.queue += [t["id"] for t in more if len(session.queue) < MAX_QUEUE]
        session.seed = session.queue[-1] if more else session.seed

    def remote_report(self, device_id: str, state: str, position: float, ended: bool) -> None:
        session = self.sessions.get(device_id)
        if session is None or device_id not in self.devices:
            return
        if state in ("playing", "paused"):
            session.anchor(position, state)
        if ended:
            asyncio.get_running_loop().create_task(self.step(session, session.base_url, 1, True))

    def view(self, session: Session) -> dict:
        track = catalog.track(session.current) if session.current is not None else None
        return {"device": session.device_id, "state": session.state, "index": session.index, "position": round(session.position(), 1),
                "duration": session.duration, "volume": session.volume, "repeat": session.repeat, "track": track,
                "queue": catalog.by_ids(session.queue[:200]), "length": len(session.queue), "error": session.error}

    async def poll_one(self, session: Session) -> None:
        device = self.devices.get(session.device_id)
        if not device or device["kind"] == "display" or session.state not in ("playing", "paused", "loading"):
            return
        try:
            info = await (dlna.status(device) if device["kind"] == "dlna" else cast_chrome.status(device))
        except RuntimeError as exc:
            session.error = str(exc)
            return
        session.error = ""
        if info["state"] in ("playing", "paused"):
            session.anchor(info["position"], info["state"])
            if info.get("duration"):
                session.duration = info["duration"]
        elif info["state"] == "stopped" and session.state == "playing" and time.time() - session.loaded_at > END_GRACE:
            await self.step(session, session.base_url, 1, True)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(POLL_PERIOD)
            for session in list(self.sessions.values()):
                try:
                    await self.poll_one(session)
                except Exception as exc:
                    log.warning("Controllo della riproduzione su %s: %s", session.device_id, exc)


outputs = Outputs()
