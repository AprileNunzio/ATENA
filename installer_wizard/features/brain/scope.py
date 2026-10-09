import ipaddress
import urllib.parse
from typing import Mapping

from features.cloud.catalog import is_cloud, is_server, parse_ref

LOCAL, SERVER, CLOUD = "local", "server", "cloud"
SCOPES = ("anywhere", "home_first", "home")
STRATEGIES = ("order", "fastest")
DEFAULT_SCOPE, DEFAULT_STRATEGY = "anywhere", "order"


def private_url(url: str) -> bool:
    host = (urllib.parse.urlparse(url if "//" in url else f"http://{url}").hostname or "").lower()
    if host == "localhost" or host.endswith((".local", ".lan", ".home.arpa", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def origin(ref: str) -> str:
    if not is_cloud(ref):
        return LOCAL
    try:
        provider, _ = parse_ref(ref)
    except ValueError:
        return CLOUD
    if is_server(provider):
        return SERVER
    from features.cloud.vault import vault
    base = str(vault.get(provider).get("base_url") or "")
    return SERVER if base and private_url(base) else CLOUD


def clean_scope(value: str | None) -> str:
    return value if value in SCOPES else DEFAULT_SCOPE


def clean_strategy(value: str | None) -> str:
    return value if value in STRATEGIES else DEFAULT_STRATEGY


def allowed(ref: str, scope: str) -> bool:
    return scope != "home" or origin(ref) != CLOUD


def _speed_key(ref: str, index: int, stats: Mapping[str, dict]) -> tuple:
    s = stats.get(ref) or {}
    ok, fail = int(s.get("ok") or 0), int(s.get("fail") or 0)
    if fail > ok:
        return (2, index, 0)
    if ok:
        return (0, float(s.get("avg_ms") or 0), index)
    return (1, index, 0)


def _arrange(refs: list[str], strategy: str, stats: Mapping[str, dict]) -> list[str]:
    if strategy != "fastest":
        return refs
    return [r for _, r in sorted(enumerate(refs), key=lambda p: _speed_key(p[1], p[0], stats))]


def apply(order: list[str], scope: str, strategy: str = DEFAULT_STRATEGY,
          stats: Mapping[str, dict] | None = None) -> list[str]:
    stats = stats or {}
    refs = [r for r in dict.fromkeys(order) if allowed(r, scope)]
    if scope != "home_first":
        return _arrange(refs, strategy, stats)
    home = [r for r in refs if origin(r) != CLOUD]
    cloud = [r for r in refs if origin(r) == CLOUD]
    return _arrange(home, strategy, stats) + _arrange(cloud, strategy, stats)
