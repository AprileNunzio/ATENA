# flake8: noqa: E402
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI

import bus_api
import licensing_api
import health
from loops import supervisor as loop_supervisor
import pages
import registry_api
import setup_api
import packages_api
import system_api
import updater
from config import ADMIN_PORT, DEMO, PUBLIC_PORT, VERSION, env_get
from origin_guard import OriginGuard
from atena_bus import atena_bus
from feature_registry import registry
from features.brain import api as brain_api
from features.brain import routing as brain_routing
from features.presentation import api as presentation_api
from features.secure import api as secure_api
from features.actions import api as actions_api
from features.bluetooth import api as bluetooth_api
from features.bluetooth.service import service as bluetooth_service
from features.vision.tips import tips as object_tips
from features.nodes.beacon import beacon as node_beacon
from features.chat import api as chat_api
from features.nodes import api as nodes_api
from features.cloud import api as cloud_api
from features.desktop import api as desktop_api
from features.desktop.desk import desk
from features.documents import api as documents_api
from features.devices import api as devices_api
from features.devices import audio
from features.google import api as google_api
from features.google.gservices import google
from features.home_assistant import api as home_api
from features.home_assistant import home
from features.location import api as location_api
from features.cameras import api as cameras_api
from features.models3d import api as models3d_api
from features.ear import api as ear_api
from features.automations import api as automations_api
from features.automations.engine import engine as automations_engine
from features.autonomy import api as autonomy_api
from features.avatars import api as avatars_api
from features.capabilities import api as capabilities_api
from features.habits import api as habits_api
from features.kiosk import driver as display_driver
from features.habits.service import habits
from features.governor import api as governor_api
from features.governor.service import governor
from features.scheduler import api as scheduler_api
from features.selftest import api as selftest_api
from features.shares import api as shares_api
from features.vault import api as vault_api
from features.vault.service import vault
from features.selftest.service import selftest
from features.sounds import api as sounds_api
from features.autonomy.engine import autonomy
from features.cameras import autosetup as cameras_autosetup
from features.cameras import controls as cameras_controls
from features.cameras import motion as cameras_motion
from features.cameras.recorder import recorder as cameras_recorder
from features.laws import api as laws_api
from features.maps import api as maps_api
from features.mind import api as mind_api
from features.authz import api as authz_api
from features.locale import api as locale_api
from features.maps.maps import maps
from features.mcpclient import api as mcpclient_api
from features.mcpclient.service import run as mcpclient_run
from features.music import api as music_api
from features.music import api_library as music_library_api
from features.music import api_play as music_play_api
from features.music import api_playlists as music_playlists_api
from features.music import api_share as music_share_api
from features.music import subsonic as music_subsonic_api
from features.music.outputs import outputs as music_outputs
from features.music.service import library as music_library
from features.network import api as network_api
from features.network.explorer import explorer
from features.people import api as people_api
from features.people import presence
from features.skills import api as skills_api
from features.soup import api as soup_api
from features.spotify import api as spotify_api
from features.spotify.spotify import spotify
from features.study import api as study_api
from features.study import study
from features.team import api as team_api
from features.telegram import api as telegram_api
from features.understanding import api as understanding_api
from features.telegram.bot import bot
from features.vision import api as vision_api
from features.vision.nightly import loop as nightly_biometrics_loop
from features.whiteboard import api as whiteboard_api
from features.printers import api as printers_api
from features.rpa import api as rpa_api
from features.nvr import api as nvr_api
from features.nvr.service import nvr as nvr_service
from features.scene import api as scene_api
from features.scene.service import scene as scene_service
from features.twin import api as twin_api
from features.vision.webcams import webcams
from features.voices import api as voices_api
from orchestrator import orch, telemetry_loop

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("atena.supervisor")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

FEATURE_APIS = (
    secure_api,
    presentation_api,
    actions_api,
    bluetooth_api,
    chat_api,
    cloud_api,
    voices_api,
    vision_api,
    devices_api,
    location_api,
    people_api,
    music_api,
    music_library_api,
    music_playlists_api,
    music_play_api,
    music_share_api,
    music_subsonic_api,
    study_api,
    soup_api,
    network_api,
    telegram_api,
    home_api,
    brain_api,
    desktop_api,
    spotify_api,
    google_api,
    maps_api,
    skills_api,
    nodes_api,
    mind_api,
    authz_api,
    locale_api,
    laws_api,
    cameras_api,
    models3d_api,
    documents_api,
    ear_api,
    autonomy_api,
    avatars_api,
    automations_api,
    sounds_api,
    selftest_api,
    habits_api,
    vault_api,
    shares_api,
    scheduler_api,
    governor_api,
    capabilities_api,
    team_api,
    mcpclient_api,
    whiteboard_api,
    understanding_api,
    printers_api,
    rpa_api,
    nvr_api,
    twin_api,
    scene_api,
)


def build(admin: bool) -> FastAPI:
    title = "Atena OS Admin" if admin else "Atena OS"
    app = FastAPI(title=title, docs_url=None, redoc_url=None, openapi_url=None)
    if admin:
        pages.mount_static(app, "shared", "admin")
    else:
        pages.mount_static(app, "shared", "display", "monitor", "screen", "setup")

    web_dir = Path(__file__).resolve().parent.parent.parent / "server" / "web"
    if web_dir.exists():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        app.mount(
            "/static/dualbrain",
            StaticFiles(directory=str(web_dir)),
            name="static-dualbrain",
        )
        if not admin:

            @app.get("/web")
            async def serve_dualbrain_web():
                return FileResponse(str(web_dir / "index.html"))

    kind = "admin_routes" if admin else "public_routes"
    for module in (*FEATURE_APIS, bus_api, licensing_api, registry_api, pages, setup_api, packages_api, system_api):
        routes = getattr(module, kind, None)
        if routes is not None:
            app.include_router(routes)

    if admin:
        try:
            from server.web.features.computer_control.api import router as computer_control_router
        except ImportError as exc:
            log.error("Router computer_control non caricato: %s", exc)
        else:
            app.include_router(computer_control_router)

    allowed = f'{env_get("ATENA_ALLOWED_HOSTS")},{os.environ.get("ATENA_ALLOWED_HOSTS", "")}'
    app.add_middleware(OriginGuard, extra_hosts=allowed.split(","))
    return app


public = build(admin=False)
admin = build(admin=True)


def secure_server():
    import tls
    from config import STATE_DIR

    port = int(os.environ.get("ATENA_TLS_PORT", 8002 if DEMO else 443))
    try:
        material = tls.ensure_certificates(
            STATE_DIR / "tls", tls.local_names(), tls.local_addresses()
        )
        server = uvicorn.Server(
            uvicorn.Config(
                public,
                host="0.0.0.0",
                port=port,
                log_level="warning",
                ssl_certfile=str(material.cert),
                ssl_keyfile=str(material.key),
                timeout_graceful_shutdown=3,
            )
        )
    except Exception as exc:
        log.warning("HTTPS non disponibile: %s", exc)
        return None
    secure_api.announce(port)
    return server


async def serve_optional(server) -> None:
    try:
        await server.serve()
    except (SystemExit, Exception) as exc:
        log.warning("Il server HTTPS si è fermato: %s", exc)


BACKGROUND = (
    ("telemetria", telemetry_loop, 0.0),
    ("risorse", governor.run, 0.0),
    ("webcam", webcams.run, 0.0),
    ("avvio", orch.boot, 0.0),
    ("controllo-salute", lambda: health.Watchdog(orch).run(), 0.0),
    ("aggiornamenti", updater.scheduler, 0.0),
    ("presenze", presence.monitor.run, 0.0),
    ("telegram", bot.run, 0.0),
    ("rete", explorer.run, 0.0),
    ("audio", audio.watcher.run, 0.0),
    ("studio", study.engine.run, 0.0),
    ("addestramento", soup_api.trainer.run, 0.0),
    ("funzionalita", registry.run, 0.0),
    ("scrivania", desk.run, 0.0),
    ("spotify", spotify.run, 0.0),
    ("google", google.run, 0.0),
    ("mappe", maps.run, 0.0),
    ("casa", home.brain.run, 0.0),
    ("bluetooth", bluetooth_service.run, 0.0),
    ("oggetti", object_tips.run, 0.0),
    ("nodi", node_beacon.run, 0.0),
    ("registrazioni-camere", cameras_recorder.run, 0.0),
    ("movimento-camere", cameras_motion.run, 0.0),
    ("controlli-webcam", cameras_controls.run, 0.0),
    ("auto-infrarosso", cameras_autosetup.run, 0.0),
    ("autonomia", autonomy.run, 0.0),
    ("automazioni", automations_engine.run, 60.0),
    ("autotest", selftest.loop, 0.0),
    ("abitudini", habits.run, 0.0),
    ("bus", atena_bus.run, 0.0),
    ("nvr", nvr_service.run, 0.0),
    ("scena", scene_service.run, 0.0),
    ("cassaforte", vault.run, 0.0),
    ("schermo", display_driver.guard, 0.0),
    ("cervello", brain_routing.run, 0.0),
    ("musica", music_library.run, 0.0),
    ("uscite-musica", music_outputs.run, 0.0),
    ("mcp-esterni", mcpclient_run, 0.0),
    ("ottimizzazione-biometrica", nightly_biometrics_loop, 0.0),
)


async def main() -> None:
    servers = [
        uvicorn.Server(
            uvicorn.Config(
                public,
                host="0.0.0.0",
                port=PUBLIC_PORT,
                log_level="warning",
                timeout_graceful_shutdown=3,
            )
        ),
        uvicorn.Server(
            uvicorn.Config(
                admin,
                host="0.0.0.0",
                port=ADMIN_PORT,
                log_level="warning",
                timeout_graceful_shutdown=3,
            )
        ),
    ]
    https = secure_server()
    log.info(
        "Atena OS Supervisor v%s — utente :%d — admin :%d%s",
        VERSION,
        PUBLIC_PORT,
        ADMIN_PORT,
        " (DEMO)" if DEMO else "",
    )
    for name, factory, period in BACKGROUND:
        loop_supervisor.add(name, factory, period)
    tasks = [asyncio.create_task(loop_supervisor.run())]
    try:
        await asyncio.gather(
            *(s.serve() for s in servers), *([serve_optional(https)] if https else [])
        )
    finally:
        for t in tasks:
            t.cancel()
        study.engine.save()


if __name__ == "__main__":
    asyncio.run(main())
