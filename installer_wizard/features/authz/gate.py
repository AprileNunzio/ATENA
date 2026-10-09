from state import store

from features.authz import risk as risks
from features.authz.policy import Decision, policy
from features.authz.principal import Strength, acting
from features.authz.risk import Risk

REFUSALS = {
    "role": "Mi dispiace, il profilo di chi mi parla non è autorizzato a questa operazione.",
    Strength.WEAK: "Per questa operazione devo prima capire chi sei: avvicinati o parlami così posso riconoscerti.",
    Strength.SINGLE: "Per questa operazione devo prima riconoscerti con sicurezza: guarda la telecamera o parlami così riconosco la tua voce.",
    Strength.STRONG: ("È un'operazione delicata: mi serve il riconoscimento di volto e voce insieme, "
                      "oppure chiedila dal pannello di amministrazione."),
}


class Forbidden(PermissionError):

    def __init__(self, decision: Decision) -> None:
        super().__init__(refusal(decision))
        self.decision = decision


def refusal(decision: Decision) -> str:
    if decision.code == "role":
        return REFUSALS["role"]
    return REFUSALS.get(decision.needed, REFUSALS[Strength.STRONG])


def _audit(kind: str, name: str, decision: Decision) -> None:
    who = acting()
    store.event("WARN", f"Autorizzazione negata · {kind} «{name}» ({decision.risk.name.lower()}) a "
                        f"{who.slug or 'sconosciuto'} [{who.role}, {who.strength.name.lower()}, {'+'.join(who.factors) or '-'}]: "
                        f"{decision.code}", "authz")


def check(kind: str, name: str, level: Risk) -> Decision:
    decision = policy.check(acting(), level)
    if not decision.allowed:
        _audit(kind, name, decision)
    return decision


def tool(name: str) -> Decision:
    return check("strumento", name, risks.of_tool(name))


def connector(name: str) -> Decision:
    return check("funzione", name, risks.of_connector(name))


def require_tool(name: str) -> None:
    decision = tool(name)
    if not decision.allowed:
        raise Forbidden(decision)


def within_role(name: str) -> bool:
    return risks.of_tool(name) <= policy.limit(acting())


def connector_allowed(name: str) -> bool:
    return policy.check(acting(), risks.of_connector(name)).allowed
