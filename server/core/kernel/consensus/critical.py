import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

from server.core.kernel.consensus.ballot import Ballot
from server.core.kernel.domain.dag import ExecutionDag
from server.core.kernel.domain.node import NodeKind, NodeSpec, RiskLevel

_GATE_WORDS = re.compile(r"garage|gate|cancell|portone|door|porta|basculante|serrand", re.IGNORECASE)
_ALARM_WORDS = re.compile(r"alarm|allarm|antifurto|security|sicurezza", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")
_NEGATIONS = frozenset({"non", "mai", "never", "don", "dont", "not", "no"})

_VERBS: Dict[str, FrozenSet[str]] = {
    "unlock": frozenset({"apri", "aprire", "apra", "sblocca", "sbloccare", "sblocchi", "unlock", "open", "entrare"}),
    "open": frozenset({"apri", "aprire", "apra", "unlock", "open", "alza", "alzare", "solleva"}),
    "disarm": frozenset({"disattiva", "disattivare", "disarma", "disarmare", "disinserisci", "disinserire", "spegni",
                         "spegnere", "togli", "togliere", "disable", "disarm", "off"}),
    "silence": frozenset({"spegni", "spegnere", "silenzia", "zitta", "ferma", "fermare", "stop", "disattiva", "off"}),
}
_NOUNS: Dict[str, FrozenSet[str]] = {
    "lock": frozenset({"porta", "portone", "serratura", "chiave", "ingresso", "door", "lock", "casa"}),
    "alarm_control_panel": frozenset({"allarme", "antifurto", "alarm", "sicurezza"}),
    "cover": frozenset({"garage", "cancello", "basculante", "portone", "porta", "serranda", "gate", "door"}),
    "valve": frozenset({"valvola", "acqua", "gas", "rubinetto", "valve", "water"}),
    "siren": frozenset({"sirena", "allarme", "siren", "alarm"}),
    "switch": frozenset({"allarme", "antifurto", "alarm", "sirena"}),
}


@dataclass(frozen=True)
class CriticalAction:
    domain: str
    service: str
    entity_id: str
    utterance: str
    origin: str = "agent"
    data: Mapping[str, object] = field(default_factory=dict)

    @property
    def target(self) -> str:
        return f"{self.domain}.{self.service} su {self.entity_id}"

    def describe(self) -> str:
        return (
            f"Richiesta originale dell'utente: «{self.utterance[:300]}». "
            f"Azione fisica proposta dall'agente «{self.origin}»: {self.target} con dati {dict(self.data)}."
        )

    def to_dag(self) -> ExecutionDag:
        return ExecutionDag.build([NodeSpec("critical_action", NodeKind.DESTRUCTIVE_IO, self.describe(), risk=RiskLevel.DESTRUCTIVE)])


_GENERIC_DOMAINS = frozenset({"homeassistant", "script", "scene", "automation"})
_BY_ENTITY = {"lock": "unlock", "alarm_control_panel": "disarm", "valve": "open", "siren": "silence"}


def _generic_class(service: str, entity_id: str) -> Optional[str]:
    for entity in (e.strip().lower() for e in entity_id.split(",")):
        domain = entity.split(".", 1)[0]
        if domain in _BY_ENTITY:
            return _BY_ENTITY[domain]
        if domain == "cover" and _GATE_WORDS.search(entity):
            return "open"
        if _ALARM_WORDS.search(entity) and service in ("turn_off", "toggle"):
            return "disarm"
    return None


def effective_domain(domain: str, entity_id: str) -> str:
    domain = domain.lower()
    if domain in _GENERIC_DOMAINS and "." in entity_id:
        return entity_id.split(",")[0].strip().lower().split(".", 1)[0]
    return domain


def action_class(domain: str, service: str, entity_id: str) -> Optional[str]:
    domain, service = domain.lower(), service.lower()
    if domain in _GENERIC_DOMAINS:
        return _generic_class(service, entity_id)
    if domain == "lock" and service in ("unlock", "open"):
        return "unlock"
    if domain == "alarm_control_panel" and service == "alarm_disarm":
        return "disarm"
    if domain == "cover" and service in ("open_cover", "set_cover_position", "toggle") and _GATE_WORDS.search(entity_id):
        return "open"
    if domain == "valve" and service in ("open_valve", "set_valve_position", "toggle"):
        return "open"
    if domain == "siren" and service in ("turn_off", "toggle"):
        return "silence"
    if domain in ("switch", "input_boolean") and service in ("turn_off", "toggle") and _ALARM_WORDS.search(entity_id):
        return "disarm"
    return None


def is_critical(domain: str, service: str, entity_id: str) -> bool:
    return action_class(domain, service, entity_id) is not None


def _words(text: str) -> Tuple[str, ...]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return tuple(_WORD.findall(plain.replace("'", " ")))


class IntentConsistencyVoter:
    name = "intent_consistency"
    can_veto = True

    def __init__(self, action: CriticalAction) -> None:
        self._action = action

    async def vote(self, dag: ExecutionDag) -> Ballot:
        kind = action_class(self._action.domain, self._action.service, self._action.entity_id)
        if kind is None:
            return Ballot(self.name, True, "not a critical action")
        words = _words(self._action.utterance)
        verbs = [i for i, w in enumerate(words) if w in _VERBS[kind]]
        if not verbs:
            return Ballot(self.name, False, f"the user never asked to {kind}: the proposal is not grounded in the request")
        if all(any(w in _NEGATIONS for w in words[max(0, i - 3):i]) for i in verbs):
            return Ballot(self.name, False, "the request is negated")
        target = {w for e in self._action.entity_id.split(",") for w in _words(e.split(".", 1)[-1].replace("_", " "))}
        nouns = _NOUNS.get(effective_domain(self._action.domain, self._action.entity_id), frozenset())
        if not (set(words) & (nouns | {t for t in target if len(t) >= 3})):
            return Ballot(self.name, False, f"the request does not mention {self._action.entity_id}")
        return Ballot(self.name, True, "the proposal matches the literal request")
