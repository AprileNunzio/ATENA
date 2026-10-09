import re
import time
import urllib.parse

from config import PUBLIC_PORT

from features.tv import relay
from features.tv.m3u import norm

TARGET = re.compile(r"^(display(:\d{1,2})?|pc:[a-z0-9][a-z0-9-]{2,47}|(cast|dlna):[A-Za-z0-9._-]{1,64})$")
ONLINE_FOR = 90.0
CASTING: dict[str, float] = {}


class TargetError(ValueError):
    pass


def base_url() -> str:
    from features.actions.common import my_ip
    return f"http://{my_ip()}" + ("" if PUBLIC_PORT == 80 else f":{PUBLIC_PORT}")


def watch_path(channel: dict) -> str:
    token = relay.token_for(channel["id"])
    query = urllib.parse.urlencode({"c": channel["id"], "t": token, "n": channel["name"][:60]})
    return f"/tv/watch?{query}"


def live_path(channel: dict) -> str:
    return f"/api/tv/live/{channel['id']}?t={urllib.parse.quote(relay.token_for(channel['id']))}"


def _pcs() -> list[dict]:
    from features.nodes.registry import registry
    now = time.time()
    return [{"id": f"pc:{n['id']}", "kind": "pc", "name": n["name"], "room": n.get("room", ""),
             "online": now - n.get("last_seen", 0) < ONLINE_FOR}
            for n in registry.data["nodes"].values() if n.get("type") == "desktop"]


def _screens() -> list[dict]:
    from features.desktop.screens import screens
    rows = [{"id": "display", "kind": "display", "name": "Schermi di Atena", "online": True}]
    active = screens.active()
    if len(active) > 1:
        rows += [{"id": f"display:{s['n']}", "kind": "display", "name": f"Schermo {s['n'] + 1}", "online": True} for s in active]
    return rows


async def listing(discover: bool = False) -> list[dict]:
    from features.music.outputs import outputs
    devices = await outputs.refresh(discover)
    casts = [{"id": d["id"], "kind": d["kind"], "name": d["name"], "online": True} for d in devices if d["kind"] in ("cast", "dlna")]
    return _screens() + _pcs() + casts


def resolve(text: str, rows: list[dict]) -> dict | None:
    flat = f" {norm(text)} "
    named = [r for r in rows if r["kind"] != "display" and f" {norm(r['name'])} " in flat]
    if named:
        return max(named, key=lambda r: len(r["name"]))
    if re.search(r" (pc|computer|portatile|desktop) ", flat):
        return next((r for r in rows if r["kind"] == "pc" and r["online"]), None)
    if re.search(r" (chromecast|cast) ", flat):
        return next((r for r in rows if r["kind"] == "cast"), None)
    if re.search(r" (tv|televisore|televisione) ", flat):
        return next((r for r in rows if r["kind"] in ("dlna", "cast")), None)
    return None


async def play(channel: dict, target_id: str, who: str = "") -> str:
    if not TARGET.match(target_id or ""):
        raise TargetError("Destinazione non valida")
    kind, _, ref = target_id.partition(":")
    if kind == "display":
        from features.desktop.desk import desk
        desk.show("tv_player", {"channel": channel["id"], "name": channel["name"], "group": channel.get("group", ""),
                                "src": live_path(channel)}, key="tv", ttl=0, priority=72)
        if ref:
            desk.set_screen("tv_player", int(ref))
        desk.fullscreen("tv", True)
        return "sullo schermo di Atena"
    if kind == "pc":
        from features.nodes.inbox import inbox
        pc = next((p for p in _pcs() if p["id"] == target_id), None)
        if not pc:
            raise TargetError("PC sconosciuto")
        if not pc["online"]:
            raise TargetError(f"Il PC {pc['name']} non è collegato in questo momento")
        inbox.push(ref, {"type": "tv", "url": base_url() + watch_path(channel), "title": channel["name"], "by": who[:40]})
        return f"sul PC {pc['name']}"
    from features.music import cast_chrome, dlna
    from features.music.outputs import outputs
    try:
        device = outputs.device(target_id)
    except KeyError as exc:
        raise TargetError("Dispositivo non trovato: cercalo di nuovo nella rete") from exc
    url = base_url() + live_path(channel)
    meta = {"title": channel["name"], "artist": channel.get("group", ""), "album": "Atena TV", "art": channel.get("logo", ""),
            "mime": "application/x-mpegURL", "video": True}
    try:
        if device["kind"] == "cast":
            await cast_chrome.load(device, url, meta)
        else:
            await dlna.load(device, url, {**meta, "mime": "video/mp2t"})
    except RuntimeError as exc:
        raise TargetError(str(exc)) from exc
    CASTING[target_id] = time.time()
    return f"su {device['name']}"


def stop_display() -> None:
    from features.desktop.desk import desk
    desk.hide(key="tv")
