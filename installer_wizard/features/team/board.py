import time
from collections import deque
from contextvars import ContextVar

from features.team import priority

ACTING: ContextVar[str] = ContextVar("team_acting", default="agent")
ACTIVITY_TTL = 90.0
CLAIM_TTL = 600.0
KEEP = 120


class Board:

    def __init__(self) -> None:
        self.doing: dict[str, dict] = {}
        self.claims: dict[str, dict] = {}
        self.messages: deque = deque(maxlen=KEEP)
        self.inbox: dict[str, list[dict]] = {}

    def begin(self, agent: str, what: str) -> None:
        self.doing[agent] = {"what": what[:200], "since": time.time()}

    def end(self, agent: str, result: str = "") -> None:
        row = self.doing.pop(agent, None)
        if row and result:
            self.post(agent, "tutti", f"ho finito: {row['what']} → {result[:120]}", "esito")

    def current(self) -> dict[str, dict]:
        cutoff = time.time() - ACTIVITY_TTL
        for key in [k for k, v in self.doing.items() if v["since"] < cutoff]:
            self.doing.pop(key)
        return dict(self.doing)

    def post(self, sender: str, to: str, text: str, kind: str = "messaggio") -> dict:
        row = {"at": time.time(), "from": sender, "to": to, "text": str(text)[:400], "kind": kind}
        self.messages.append(row)
        if to != "tutti":
            self.inbox.setdefault(to, []).append(row)
            del self.inbox[to][:-20]
        return row

    def read(self, agent: str) -> list[dict]:
        return self.inbox.pop(agent, [])

    def claim(self, agent: str, resource: str) -> str | None:
        now = time.time()
        held = self.claims.get(resource)
        if held and held["agent"] != agent and now - held["at"] < CLAIM_TTL and priority.of(held["agent"]) > priority.of(agent):
            return held["agent"]
        if held and held["agent"] != agent and now - held["at"] < CLAIM_TTL:
            self.post(agent, held["agent"], f"prendo io «{resource}» (priorità {priority.of(agent)} su {priority.of(held['agent'])})", "priorità")
        self.claims[resource] = {"agent": agent, "at": now}
        return None

    def release(self, agent: str, resource: str) -> None:
        if self.claims.get(resource, {}).get("agent") == agent:
            self.claims.pop(resource)

    def digest(self) -> str:
        rows = [f"- {a} ({priority.of(a)}): {v['what']}" for a, v in sorted(self.current().items(), key=lambda x: -priority.of(x[0]))]
        recent = [f"- {m['from']} → {m['to']}: {m['text']}" for m in list(self.messages)[-6:]]
        return ("Cosa stanno facendo ora gli altri agenti:\n" + ("\n".join(rows) or "- nessuno") +
                "\nUltimi messaggi tra agenti:\n" + ("\n".join(recent) or "- nessuno"))


board = Board()
