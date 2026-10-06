import json
import re
import secrets
import time
from urllib.parse import urlparse

from config import STATE_DIR

FILE = STATE_DIR / "mcp_servers.json"
MAX_SERVERS = 12
NAME = re.compile(r"^[^\n\r]{2,40}$")


def load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(FILE)


def check_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("indirizzo non valido: serve http(s)://host/percorso senza nome utente")
    return parsed.geturl()


def add(name: str, url: str, token: str = "", trusted: bool = False) -> str:
    data = load()
    if len(data) >= MAX_SERVERS:
        raise ValueError("Troppi server collegati")
    if not NAME.match(str(name).strip()):
        raise ValueError("nome non valido")
    server_id = "s" + secrets.token_hex(3)
    data[server_id] = {"name": str(name).strip(), "url": check_url(url), "token": str(token).strip()[:400], "trusted": bool(trusted), "enabled": True,
                       "added": time.time(), "status": "mai controllato", "tools": 0, "checked": 0}
    save(data)
    return server_id


def update(server_id: str, **fields) -> None:
    data = load()
    if server_id in data:
        data[server_id].update(fields)
        save(data)


def remove(server_id: str) -> bool:
    data = load()
    found = data.pop(server_id, None) is not None
    if found:
        save(data)
    return found


def public(row_id: str, row: dict) -> dict:
    return {"id": row_id, "name": row["name"], "url": row["url"], "trusted": row["trusted"], "enabled": row["enabled"], "has_token": bool(row["token"]),
            "status": row["status"], "tools": row["tools"], "checked": row["checked"]}
