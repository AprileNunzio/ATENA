import asyncio
import logging
import shutil
import sys

from config import env_get, write_env

from features.locale import service
from features.locale.store import store
from features.voices import languages

CHECK_EVERY = 600.0
KEY = "ATENA_EAR_LANGUAGES"
log = logging.getLogger("atena.locale")


def household() -> list[str]:
    from features.people import people
    found = {service.system_reply()}
    for profile in people.all_profiles(light=True):
        lang = str(profile.get("voice_language") or "")
        if lang in languages.LANGS:
            found.add(lang)
    for scope in ("people", "devices"):
        for entry in store.entries(scope):
            found.update(v for k, v in entry.items() if k in ("reply", "teach") and v in languages.LANGS)
    return sorted(found)


async def sync() -> bool:
    wanted = ",".join(household())
    if env_get(KEY, "") == wanted:
        return False
    write_env({KEY: wanted})
    log.info("Lingue ascoltate dall'orecchio: %s", wanted)
    if sys.platform.startswith("linux") and shutil.which("systemctl"):
        process = await asyncio.create_subprocess_exec("systemctl", "try-restart", "atena-ear",
                                                       stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await process.wait()
    return True


async def run() -> None:
    while True:
        try:
            await sync()
        except (OSError, ValueError) as exc:
            log.warning("Lingue della casa non sincronizzate: %s", exc)
        await asyncio.sleep(CHECK_EVERY)
