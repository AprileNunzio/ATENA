import json
import logging
import subprocess
import threading
import urllib.error
import urllib.request

from settings import paths
from updates import manifest

log = logging.getLogger("atena.updates")
RELEASES = f"https://api.github.com/repos/{manifest.REPOSITORY}/releases?per_page=20"
CHECK_EVERY = 6 * 3600
FIRST_CHECK = 300
TIMEOUT = 30
SILENT = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]


def _get(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ATENA-Assistente", "Accept": "application/octet-stream"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise manifest.UpdateRejected(f"risposta troppo grande da {url}")
    return data


def _assets(release: dict) -> dict[str, str]:
    return {a.get("name", ""): a.get("browser_download_url", "") for a in release.get("assets") or []}


def latest() -> tuple[str, dict[str, str]] | None:
    releases = json.loads(_get(RELEASES, 2_000_000).decode("utf-8"))
    candidates = []
    for release in releases if isinstance(releases, list) else []:
        tag = str(release.get("tag_name", ""))
        assets = _assets(release)
        if tag.startswith("assistant-v") and not release.get("draft") and {"manifest.json", "manifest.sig"} <= set(assets):
            try:
                candidates.append((manifest.version_key(tag.removeprefix("assistant-v")), tag, assets))
            except manifest.UpdateRejected:
                log.warning("Release con versione non valida ignorata: %s", tag)
    if not candidates:
        return None
    _key, tag, assets = max(candidates)
    return tag.removeprefix("assistant-v"), assets


class Updater(threading.Thread):
    def __init__(self, notify, after_launch) -> None:
        super().__init__(daemon=True, name="updates")
        self.notify, self.after_launch = notify, after_launch
        self.wake = threading.Event()
        self.stop_flag = threading.Event()

    def check_now(self) -> None:
        self.wake.set()

    def run(self) -> None:
        if not paths.FROZEN:
            log.info("Aggiornamenti automatici attivi solo nella versione installata")
            return
        self.wake.wait(FIRST_CHECK)
        while not self.stop_flag.is_set():
            self.wake.clear()
            try:
                self.cycle()
            except manifest.UpdateRejected as exc:
                log.error("Aggiornamento rifiutato: %s", exc)
                self.notify(f"🛑 Aggiornamento rifiutato per sicurezza: {exc}")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                log.info("Controllo aggiornamenti non riuscito: %s", exc)
            self.wake.wait(CHECK_EVERY)

    def cycle(self) -> None:
        found = latest()
        if not found or not manifest.newer(found[0], paths.VERSION):
            return
        version, assets = found
        release = manifest.verify(_get(assets["manifest.json"], 65536), _get(assets["manifest.sig"], 4096))
        if release.version != version:
            raise manifest.UpdateRejected("la versione firmata non corrisponde alla release")
        installer = _get(release.url, release.size)
        manifest.check_file(installer, release)
        target = paths.DATA_DIR / "updates" / f"ATENA_Assistente_Setup_{release.version}.exe"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(installer)
        log.info("Aggiornamento %s verificato (firma e SHA-256): installazione", release.version)
        self.notify(f"⬆ Aggiornamento {release.version} verificato: installo e riavvio ATENA…")
        subprocess.Popen([str(target), *SILENT], close_fds=True)
        self.after_launch()

    def stop(self) -> None:
        self.stop_flag.set()
        self.wake.set()
