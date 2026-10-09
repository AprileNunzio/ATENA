import re
import time
from dataclasses import dataclass

import httpx

from config import env_get

HOST = re.compile(r"^(?:\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]{1,253})(?::\d{1,5})?$")
NODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,62}$")
TOKEN_ID = re.compile(r"^[\w.-]+@[\w.-]+![\w.-]+$")
KINDS = ("qemu", "lxc")
ACTIONS = ("start", "shutdown", "stop", "reboot", "suspend", "resume")
TICKET_TTL = 7000.0
TIMEOUT = 20.0


class ProxmoxError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    host: str
    user: str
    password: str
    token_id: str
    token_secret: str
    verify: bool

    @property
    def base(self) -> str:
        host = self.host if ":" in self.host.split("]")[-1] else f"{self.host}:8006"
        return f"https://{host}/api2/json"

    @property
    def uses_token(self) -> bool:
        return bool(self.token_id and self.token_secret)


def settings() -> Settings:
    host = env_get("PROXMOX_HOST", "").strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    return Settings(host, env_get("PROXMOX_USER", "").strip(), env_get("PROXMOX_PASSWORD", ""),
                    env_get("PROXMOX_TOKEN_ID", "").strip(), env_get("PROXMOX_TOKEN_SECRET", ""),
                    env_get("PROXMOX_VERIFY_SSL", "0").strip().lower() in ("1", "true", "on", "si", "sì"))


def validate(s: Settings) -> None:
    if not s.host:
        raise ProxmoxError("Proxmox non configurato: indica l'indirizzo dell'host nelle impostazioni")
    if not HOST.match(s.host):
        raise ProxmoxError("Indirizzo dell'host Proxmox non valido")
    if s.uses_token:
        token = s.token_id if "!" in s.token_id else f"{s.user}!{s.token_id}"
        if not TOKEN_ID.match(token):
            raise ProxmoxError("Token ID non valido (formato utente@realm!nome)")
    elif not (s.user and s.password):
        raise ProxmoxError("Servono utente e password oppure un token API")


class ProxmoxClient:

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport
        self.ticket: dict = {}

    def _client(self, s: Settings) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=s.base, verify=s.verify, timeout=TIMEOUT, transport=self.transport)

    async def _auth(self, client: httpx.AsyncClient, s: Settings, write: bool) -> dict:
        if s.uses_token:
            token = s.token_id if "!" in s.token_id else f"{s.user}!{s.token_id}"
            return {"Authorization": f"PVEAPIToken={token}={s.token_secret}"}
        if not self.ticket or self.ticket.get("user") != s.user or time.time() - self.ticket["at"] > TICKET_TTL:
            r = await client.post("/access/ticket", data={"username": s.user, "password": s.password})
            if r.status_code == 401:
                raise ProxmoxError("Credenziali Proxmox rifiutate")
            r.raise_for_status()
            data = r.json().get("data") or {}
            self.ticket = {"user": s.user, "at": time.time(), "cookie": data.get("ticket", ""),
                           "csrf": data.get("CSRFPreventionToken", "")}
        headers = {"Cookie": f"PVEAuthCookie={self.ticket['cookie']}"}
        if write:
            headers["CSRFPreventionToken"] = self.ticket["csrf"]
        return headers

    async def call(self, method: str, path: str, data: dict | None = None):
        s = settings()
        validate(s)
        try:
            async with self._client(s) as client:
                headers = await self._auth(client, s, method != "GET")
                payload = {"params": data} if method == "GET" else {"data": data}
                r = await client.request(method, path, headers=headers, **payload)
                if r.status_code == 401:
                    self.ticket = {}
                    raise ProxmoxError("Accesso a Proxmox negato: controlla utente, token e permessi")
                if r.status_code >= 400:
                    raise ProxmoxError(f"Proxmox ha risposto {r.status_code}: {r.text[:200]}")
                return r.json().get("data")
        except httpx.HTTPError as exc:
            raise ProxmoxError(f"Proxmox non raggiungibile: {exc}") from exc

    async def overview(self) -> dict:
        nodes = await self.call("GET", "/nodes") or []
        guests = await self.call("GET", "/cluster/resources", {"type": "vm"}) or []
        keep_node = ("node", "status", "cpu", "maxcpu", "mem", "maxmem", "uptime")
        keep_guest = ("vmid", "name", "node", "type", "status", "cpu", "maxcpu", "mem", "maxmem", "uptime", "template")
        return {"nodes": [{k: n.get(k) for k in keep_node} for n in nodes],
                "guests": sorted(({k: g.get(k) for k in keep_guest} for g in guests if not g.get("template")),
                                 key=lambda g: (str(g.get("node")), int(g.get("vmid") or 0)))}

    async def power(self, node: str, kind: str, vmid: int, action: str) -> str:
        if not NODE.match(node or "") or kind not in KINDS or action not in ACTIONS or not 100 <= int(vmid) <= 999_999_999:
            raise ProxmoxError("Richiesta Proxmox non valida")
        return str(await self.call("POST", f"/nodes/{node}/{kind}/{int(vmid)}/status/{action}") or "")

    async def snapshot(self, node: str, kind: str, vmid: int, name: str) -> str:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,39}", name or ""):
            raise ProxmoxError("Nome dello snapshot non valido (lettere, numeri, - e _)")
        if not NODE.match(node or "") or kind not in KINDS or not 100 <= int(vmid) <= 999_999_999:
            raise ProxmoxError("Richiesta Proxmox non valida")
        return str(await self.call("POST", f"/nodes/{node}/{kind}/{int(vmid)}/snapshot", {"snapname": name}) or "")


client = ProxmoxClient()
