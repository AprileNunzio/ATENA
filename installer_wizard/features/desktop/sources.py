from datetime import datetime

from state import store

READY_PHASES = ("READY", "DEGRADED")


def sun_cycle() -> dict | None:
    from features.automations import sun
    t = sun.times()
    rise, set_ = t.get("sunrise"), t.get("sunset")
    if not rise or not set_:
        return None
    now = datetime.now().astimezone()
    span = (set_ - rise).total_seconds()
    progress = max(0.0, min(100.0, (now - rise).total_seconds() * 100 / span)) if span > 0 else 0.0
    return {"sunrise": rise.strftime("%H:%M"), "sunset": set_.strftime("%H:%M"), "up": rise <= now < set_,
            "progress": round(progress, 1), "daylight_min": int(span // 60), "place": str(sun.PLACE.get("name", ""))[:60]}


def home_rooms() -> dict | None:
    from features.home_assistant import home
    brief = home.brain.brief()
    rooms = [str(r)[:40] for r in brief.get("occupied", [])][:12]
    return {"rooms": rooms} if rooms and brief.get("status") == "online" else None


def update_ready() -> dict | None:
    up = store.update or {}
    if not up.get("available") or store.phase not in READY_PHASES:
        return None
    return {"local": str(up.get("local_rev", ""))[:10], "remote": str(up.get("target_rev") or up.get("remote_rev", ""))[:10],
            "changes": [str(c)[:120] for c in (up.get("changelog") or [])][:6]}


def components_down() -> dict | None:
    if store.phase not in READY_PHASES:
        return None
    down = [{"label": str(c.get("label", k))[:60], "detail": str(c.get("detail", ""))[:120], "status": c.get("status")}
            for k, c in (store.components or {}).items() if c.get("status") == "down"]
    return {"items": down[:8]} if down else None


SOURCES = {"sun_cycle": sun_cycle, "home_rooms": home_rooms, "update_ready": update_ready, "components_down": components_down}
