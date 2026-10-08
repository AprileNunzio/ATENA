import logging
from dataclasses import dataclass, field

from permissions.catalog import BY_KEY, Level
from permissions.policy import Policy

log = logging.getLogger("atena.permissions")


class Denied(PermissionError):
    pass


@dataclass(frozen=True)
class Request:
    capability: str
    summary: str
    detail: str = ""
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Answer:
    approved: bool
    remember: bool = False


class Gate:
    def __init__(self, policy: Policy, ask) -> None:
        self.policy = policy
        self.ask = ask

    def check(self, request: Request, always_ask: bool = False) -> None:
        capability = BY_KEY[request.capability]
        level = self.policy.level(capability.key)
        if level is Level.DENY:
            log.info("Negato da impostazioni: %s · %s", capability.key, request.summary)
            raise Denied(f"«{capability.title}» è disattivato nelle impostazioni dei permessi")
        if level is Level.ALLOW and not always_ask:
            return
        answer: Answer = self.ask(capability, request)
        if not answer.approved:
            log.info("Negato dall'utente: %s · %s", capability.key, request.summary)
            raise Denied("Non autorizzato")
        if answer.remember and not always_ask:
            self.policy.set(capability.key, Level.ALLOW)
        log.info("Autorizzato dall'utente: %s · %s", capability.key, request.summary)
