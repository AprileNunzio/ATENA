import json
import sys
import time
import uuid as uuidlib

DISCOVER_SECONDS = 5
CONNECT_SECONDS = 12


def discover() -> dict:
    import zeroconf
    from pychromecast.discovery import CastBrowser, SimpleCastListener
    zc = zeroconf.Zeroconf()
    browser = CastBrowser(SimpleCastListener(), zc)
    browser.start_discovery()
    time.sleep(DISCOVER_SECONDS)
    browser.stop_discovery()
    zc.close()
    return {"devices": [{"uuid": str(uid), "name": info.friendly_name, "model": info.model_name, "host": info.host, "port": info.port}
                        for uid, info in browser.devices.items()]}


def connect(request: dict):
    import pychromecast
    target = (request["host"], int(request["port"]), uuidlib.UUID(request["uuid"]), request.get("model"), request.get("name"))
    cast = pychromecast.get_chromecast_from_host(target)
    cast.wait(timeout=CONNECT_SECONDS)
    return cast


def play(request: dict) -> dict:
    cast = connect(request)
    media = cast.media_controller
    video = bool(request.get("video"))
    meta = ({"metadataType": 0, "title": request.get("title", ""), "subtitle": request.get("artist", "")} if video else
            {"metadataType": 3, "title": request.get("title", ""), "artist": request.get("artist", ""), "albumName": request.get("album", "")})
    media.play_media(request["url"], request.get("mime", "audio/mpeg"), title=request.get("title", ""), thumb=request.get("art") or None,
                     metadata=meta, current_time=None if video else float(request.get("start") or 0), autoplay=True,
                     stream_type="LIVE" if video else "BUFFERED")
    media.block_until_active(timeout=CONNECT_SECONDS)
    return {"ok": True}


def control(request: dict) -> dict:
    cast = connect(request)
    media = cast.media_controller
    action = request["action"]
    if action == "volume":
        cast.set_volume(max(0.0, min(1.0, float(request.get("value") or 0))))
        return {"ok": True}
    media.update_status()
    time.sleep(0.5)
    if media.status.media_session_id is None or media.status.player_state == "IDLE":
        return {"ok": True, "note": "nessuna riproduzione attiva"}
    try:
        if action == "pause":
            media.pause()
        elif action == "resume":
            media.play()
        elif action == "stop":
            media.stop()
        elif action == "seek":
            media.seek(float(request.get("value") or 0))
        else:
            return {"error": "comando non valido"}
    except Exception as exc:
        if type(exc).__name__ == "RequestFailed":
            return {"ok": True, "note": "il Chromecast ha rifiutato il comando"}
        raise
    time.sleep(0.3)
    return {"ok": True}


def status(request: dict) -> dict:
    cast = connect(request)
    media = cast.media_controller
    media.update_status()
    time.sleep(0.4)
    state = {"PLAYING": "playing", "PAUSED": "paused", "BUFFERING": "loading", "IDLE": "stopped"}.get(media.status.player_state, "stopped")
    return {"state": state, "position": float(media.status.adjusted_current_time or 0), "duration": float(media.status.duration or 0),
            "idle_reason": media.status.idle_reason or "", "volume": float(cast.status.volume_level if cast.status else 0)}


COMMANDS = {"discover": lambda r: discover(), "play": play, "control": control, "status": status}


def main() -> None:
    try:
        request = json.loads(sys.argv[1])
        handler = COMMANDS[request["command"]]
        result = handler(request)
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
