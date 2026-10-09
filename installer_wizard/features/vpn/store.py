import json
import logging
import threading

from config import ETC_DIR, STATE_DIR
from sealed import SealedFile

from features.vpn import model

VPN_DIR = STATE_DIR / "vpn"
PROFILES_FILE = VPN_DIR / "profiles.json"
SECRETS = SealedFile(ETC_DIR / "vpn.vault", ETC_DIR / "vpn.key")
log = logging.getLogger("atena.vpn")


def _restore(item: dict) -> model.Profile:
    built = model.profile(item, dict(item.get("settings") or {}))
    return built


class VpnStore:

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.profiles: dict[str, model.Profile] = {}
        self.wanted: dict[str, bool] = {}
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.error("Profili VPN illeggibili: %s", exc)
            return
        profiles, wanted = {}, {}
        for item in data.get("profiles") or []:
            try:
                p = _restore(item)
            except (KeyError, TypeError, ValueError) as exc:
                log.error("Profilo VPN scartato: %s", exc)
                continue
            profiles[p.id] = p
            wanted[p.id] = bool(item.get("wanted", p.autostart))
        with self.lock:
            self.profiles, self.wanted = profiles, wanted

    def save(self) -> None:
        with self.lock:
            VPN_DIR.mkdir(parents=True, exist_ok=True)
            rows = [p.export() | {"wanted": self.wanted.get(p.id, False)} for p in self.profiles.values()]
            tmp = PROFILES_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"profiles": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(PROFILES_FILE)

    def secrets(self, pid: str) -> dict:
        with self.lock:
            return dict(SECRETS.load().get(pid) or {})

    def put_secrets(self, pid: str, values: dict) -> None:
        with self.lock:
            data = SECRETS.load()
            data[pid] = values
            SECRETS.save(data)

    def drop_secrets(self, pid: str) -> None:
        with self.lock:
            data = SECRETS.load()
            if data.pop(pid, None) is not None:
                SECRETS.save(data)

    def get(self, pid: str) -> model.Profile:
        with self.lock:
            if pid not in self.profiles:
                raise KeyError("profilo VPN sconosciuto")
            return self.profiles[pid]


store = VpnStore()
