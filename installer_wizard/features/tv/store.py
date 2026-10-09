import re
import secrets
import threading
import time

import httpx
from config import ETC_DIR
from sealed import SealedFile

from features.tv import m3u
from features.tv.m3u import PlaylistError

MAX_PLAYLISTS = 20
MAX_FAVORITES = 200
_ID = re.compile(r"^[a-f0-9]{8,16}$")


class TvStore:
    def __init__(self, vault: SealedFile) -> None:
        self._vault = vault
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._index: dict[str, dict] = {}

    def _all(self) -> dict:
        if self._data is None:
            self._data = self._vault.load() or {}
            self._data.setdefault("playlists", {})
            self._data.setdefault("favorites", [])
            self._reindex()
        return self._data

    def _reindex(self) -> None:
        self._index = {c["id"]: {**c, "playlist": pid} for pid, p in self._data["playlists"].items() for c in p.get("channels", [])}

    def _save(self) -> None:
        self._vault.save(self._data)
        self._reindex()

    def playlists(self) -> list[dict]:
        return [{k: v for k, v in p.items() if k not in ("channels", "url")} | {"has_url": bool(p.get("url"))}
                for p in self._all()["playlists"].values()]

    def channels(self) -> list[dict]:
        self._all()
        return list(self._index.values())

    def channel(self, cid: str) -> dict | None:
        self._all()
        return self._index.get(str(cid))

    def favorites(self) -> list[str]:
        return [c for c in self._all()["favorites"] if c in self._index]

    def set_favorite(self, cid: str, on: bool) -> list[str]:
        if not self.channel(cid):
            raise PlaylistError("Canale sconosciuto")
        with self._lock:
            fav = [c for c in self._all()["favorites"] if c != cid]
            self._data["favorites"] = ([cid] + fav if on else fav)[:MAX_FAVORITES]
            self._save()
        return self.favorites()

    def find(self, query: str) -> dict | None:
        fav = set(self.favorites())
        channels = sorted(self.channels(), key=lambda c: c["id"] not in fav)
        return m3u.find(channels, query)

    def add(self, name: str, url: str = "", text: str = "") -> dict:
        if len(self._all()["playlists"]) >= MAX_PLAYLISTS:
            raise PlaylistError("Troppe playlist")
        pid = secrets.token_hex(6)
        entry = {"id": pid, "name": m3u.clean_text(name, 60) or "Playlist", "url": m3u.safe_url(url) if url else "",
                 "source": "url" if url else "file", "added_at": time.time(), "refreshed_at": 0, "count": 0, "error": "",
                 "channels": []}
        if text:
            entry["channels"] = m3u.parse(text)
            entry.update(refreshed_at=time.time(), count=len(entry["channels"]))
        with self._lock:
            self._all()["playlists"][pid] = entry
            self._save()
        return {k: v for k, v in entry.items() if k not in ("channels", "url")}

    def remove(self, pid: str) -> None:
        if not _ID.match(pid):
            raise PlaylistError("Playlist sconosciuta")
        with self._lock:
            self._all()["playlists"].pop(pid, None)
            self._save()

    async def refresh(self, pid: str) -> dict:
        entry = self._all()["playlists"].get(pid)
        if not entry or not entry.get("url"):
            raise PlaylistError("Questa playlist non ha un indirizzo da aggiornare")
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "VLC/3.0"}) as client:
                async with client.stream("GET", entry["url"]) as res:
                    res.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in res.aiter_bytes():
                        size += len(chunk)
                        if size > m3u.MAX_BYTES:
                            raise PlaylistError("Playlist troppo grande")
                        chunks.append(chunk)
            channels = m3u.parse(b"".join(chunks).decode("utf-8", errors="replace"))
            update = {"channels": channels, "count": len(channels), "refreshed_at": time.time(), "error": ""}
        except (httpx.HTTPError, PlaylistError) as exc:
            update = {"error": str(exc)[:200] if isinstance(exc, PlaylistError) else f"non raggiungibile ({type(exc).__name__})"}
        with self._lock:
            self._all()["playlists"][pid].update(update)
            self._save()
        if update.get("error"):
            raise PlaylistError(update["error"])
        return {k: v for k, v in self._data["playlists"][pid].items() if k not in ("channels", "url")}

    def stale(self, every: float) -> list[str]:
        now = time.time()
        return [pid for pid, p in self._all()["playlists"].items() if p.get("url") and now - p.get("refreshed_at", 0) > every]


tv_store = TvStore(SealedFile(ETC_DIR / "tv_playlists.vault", ETC_DIR / "tv.key"))
