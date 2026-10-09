import json
import logging
import threading
from dataclasses import dataclass

from config import STATE_DIR

from features.authz.principal import Principal, Strength
from features.authz.risk import Risk, parse

POLICY_FILE = STATE_DIR / "authz" / "policy.json"
log = logging.getLogger("atena.authz")

DEFAULT_CEILING: dict[str, Risk] = {
    "system": Risk.CRITICAL, "owner": Risk.CRITICAL, "family": Risk.FILES, "staff": Risk.HOME,
    "friend": Risk.HOME, "guest": Risk.HOME, "service": Risk.INFO, "anonymous": Risk.HOME,
}
DEFAULT_PROOF: dict[Risk, Strength] = {
    Risk.INFO: Strength.NONE, Risk.HOME: Strength.NONE, Risk.PERSONAL: Strength.SINGLE,
    Risk.FILES: Strength.SINGLE, Risk.CRITICAL: Strength.STRONG,
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str
    risk: Risk
    needed: Strength = Strength.NONE


class Policy:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.ceiling = dict(DEFAULT_CEILING)
        self.proof = dict(DEFAULT_PROOF)
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.error("Policy di autorizzazione illeggibile, uso i valori sicuri predefiniti: %s", exc)
            return
        self.apply(data if isinstance(data, dict) else {})

    def apply(self, data: dict) -> None:
        ceiling, proof = dict(DEFAULT_CEILING), dict(DEFAULT_PROOF)
        for role, name in (data.get("ceiling") or {}).items():
            risk = parse(name)
            if role in ceiling and role != "system" and risk is not None:
                ceiling[role] = risk
        for name, strength in (data.get("proof") or {}).items():
            risk = parse(name)
            level = Strength.__members__.get(str(strength).upper())
            if risk is not None and level is not None and risk >= Risk.PERSONAL:
                proof[risk] = max(level, Strength.STRONG if risk == Risk.CRITICAL else Strength.WEAK)
        with self._lock:
            self.ceiling, self.proof = ceiling, proof

    def save(self, data: dict) -> dict:
        self.apply(data)
        POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = POLICY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.export(), indent=1), encoding="utf-8")
        tmp.replace(POLICY_FILE)
        return self.export()

    def export(self) -> dict:
        with self._lock:
            return {"ceiling": {role: risk.name.lower() for role, risk in self.ceiling.items()},
                    "proof": {risk.name.lower(): level.name.lower() for risk, level in self.proof.items()}}

    def limit(self, principal: Principal) -> Risk:
        with self._lock:
            base = self.ceiling.get(principal.role, self.ceiling["anonymous"])
        custom = parse(principal.override)
        return base if custom is None or principal.role == "system" else custom

    def check(self, principal: Principal, risk: Risk) -> Decision:
        with self._lock:
            needed = self.proof.get(risk, Strength.STRONG)
        if risk > self.limit(principal):
            return Decision(False, "role", risk, needed)
        if principal.strength < needed:
            return Decision(False, "proof", risk, needed)
        return Decision(True, "ok", risk, needed)


policy = Policy()
