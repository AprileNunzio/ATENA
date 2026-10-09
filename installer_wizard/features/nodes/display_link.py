import hashlib
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from features.nodes.registry import registry
from state import store

COOKIE = "atena_display"
LINK_TTL = 60
SESSION_TTL = 30 * 86400
MAX_SESSIONS = 64

public_routes = APIRouter()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class DisplayLinks:
    def __init__(self) -> None:
        self.links: dict[str, tuple[str, float]] = {}
        self.sessions: dict[str, tuple[str, float]] = {}

    def _prune(self) -> None:
        now = time.time()
        self.links = {k: v for k, v in self.links.items() if v[1] > now}
        self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}
        while len(self.sessions) > MAX_SESSIONS:
            self.sessions.pop(min(self.sessions, key=lambda k: self.sessions[k][1]))

    def issue(self, node_id: str) -> str:
        self._prune()
        token = secrets.token_urlsafe(24)
        self.links[_hash(token)] = (node_id, time.time() + LINK_TTL)
        return token

    def redeem(self, token: str) -> tuple[str, str] | None:
        self._prune()
        hit = self.links.pop(_hash(str(token or "")), None)
        if not hit:
            return None
        session = secrets.token_urlsafe(32)
        self.sessions[_hash(session)] = (hit[0], time.time() + SESSION_TTL)
        return session, hit[0]

    def node_of(self, session: str | None) -> str | None:
        if not session:
            return None
        hit = self.sessions.get(_hash(session))
        if not hit or hit[1] < time.time() or hit[0] not in registry.data.get("nodes", {}):
            return None
        return hit[0]


links = DisplayLinks()


def display_node(request: Request) -> str | None:
    return links.node_of(request.cookies.get(COOKIE))


@public_routes.post("/api/nodes/display-link")
async def node_display_link(request: Request):
    auth = request.headers.get("authorization", "")
    try:
        node = registry.authenticate(request.headers.get("x-atena-node", ""), auth.removeprefix("Bearer ").strip())
    except PermissionError as exc:
        raise HTTPException(401, str(exc))
    return {"path": f"/screen/open?t={links.issue(node['id'])}", "expires_in": LINK_TTL}


@public_routes.get("/screen/open")
async def screen_open(request: Request, t: str = ""):
    redeemed = links.redeem(t)
    if not redeemed:
        raise HTTPException(403, "Collegamento scaduto: riaprilo dall'assistente di Windows")
    session, node_id = redeemed
    store.event("INFO", f"Widget aperti sul computer {registry.data['nodes'][node_id].get('name', node_id)}", "nodes")
    res = RedirectResponse("/screen?mirror=1", status_code=303)
    res.set_cookie(COOKIE, session, max_age=SESSION_TTL, httponly=True, samesite="strict",
                   secure=request.url.scheme == "https", path="/")
    return res
