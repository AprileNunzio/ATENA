from dataclasses import dataclass

READY_PHASES = ("READY", "DEGRADED")
MAX_TODOS = 8
_SEVERITY_ORDER = {"bad": 0, "warn": 1, "info": 2}


@dataclass(frozen=True)
class Todo:
    severity: str
    text: str
    zone: str
    target: str = ""

    def as_dict(self) -> dict:
        return {"severity": self.severity, "text": self.text, "zone": self.zone, "target": self.target}


@dataclass(frozen=True)
class Inputs:
    phase: str
    progress: float
    steps: dict
    step_titles: dict
    components: dict
    features: list
    update: dict
    approvals: int
    awakening_left: int = 0


def _broken_components(components: dict) -> list[dict]:
    return [c for c in components.values() if c.get("status") == "down" and not c.get("on_demand")]


def _warn_components(components: dict) -> list[dict]:
    return [c for c in components.values() if c.get("status") == "warn" and not c.get("on_demand")]


def _failed_steps(inputs: Inputs) -> list[str]:
    return [inputs.step_titles.get(sid, sid) for sid, rec in inputs.steps.items() if rec.get("status") == "failed"]


def health(components: dict) -> int:
    relevant = [c for c in components.values() if not c.get("on_demand")]
    if not relevant:
        return 100
    score = sum(1.0 if c.get("status") == "ok" else 0.5 if c.get("status") == "warn" else 0.0 for c in relevant)
    return round(100 * score / len(relevant))


def tone(inputs: Inputs) -> str:
    if inputs.phase not in READY_PHASES:
        return "busy"
    if _broken_components(inputs.components):
        return "bad"
    if inputs.phase == "DEGRADED" or _warn_components(inputs.components) or _failed_steps(inputs):
        return "warn"
    return "ok"


def todos(inputs: Inputs) -> list[Todo]:
    items: list[Todo] = []
    if inputs.phase not in READY_PHASES:
        items.append(Todo("info", f"Installazione in corso: {round(inputs.progress)}%", "system", "steps"))
    items += [Todo("bad", f"«{c.get('label', '?')}» non funziona", "system", "steps") for c in _broken_components(inputs.components)]
    items += [Todo("bad", f"Passo «{title}» non riuscito", "system", "steps") for title in _failed_steps(inputs)]
    items += [Todo("warn", f"«{c.get('label', '?')}» funziona a metà", "system", "steps") for c in _warn_components(inputs.components)]
    if inputs.phase == "DEGRADED" and not items:
        items.append(Todo("warn", "Atena funziona in modalità ridotta", "system", "steps"))
    if inputs.approvals:
        noun = "approvazione in attesa" if inputs.approvals == 1 else "approvazioni in attesa"
        items.append(Todo("warn", f"{inputs.approvals} {noun}", "trust", "autonomy"))
    risky = [f for f in inputs.features if f.get("state", {}).get("risk")]
    items += [Todo("warn", f"«{f.get('name', f.get('id'))}» è attiva ma l'hardware non basta", "tools", f"f/{f.get('id')}") for f in risky]
    if inputs.awakening_left and inputs.phase in READY_PHASES:
        left = "manca 1 passo" if inputs.awakening_left == 1 else f"mancano {inputs.awakening_left} passi"
        items.append(Todo("info", f"Completa il Risveglio: {left}", "awakening"))
    if inputs.update.get("available"):
        items.append(Todo("info", "Aggiornamento di Atena pronto", "system", "updates"))
    items.sort(key=lambda t: _SEVERITY_ORDER.get(t.severity, 3))
    return items[:MAX_TODOS]


def headline(inputs: Inputs, active: int, total: int) -> dict:
    state = tone(inputs)
    if state == "busy":
        return {"pilot": f"Installazione in corso: {round(inputs.progress)}%", "explorer": "Mi sto preparando, manca poco!"}
    problems = len(todos(inputs))
    if state == "bad":
        return {"pilot": "Una parte importante non funziona", "explorer": "Non mi sento benissimo: qualcosa va sistemato."}
    if state == "warn":
        noun = "cosa da controllare" if problems == 1 else "cose da controllare"
        return {"pilot": f"Operativa, con {problems} {noun}", "explorer": "Sto bene, ma c'è qualcosa da sistemare."}
    return {"pilot": f"Tutti i sistemi operativi. {total} strumenti, {active} attivi.",
            "explorer": "Ciao! Sto benissimo e sono pronta ad aiutarti."}
