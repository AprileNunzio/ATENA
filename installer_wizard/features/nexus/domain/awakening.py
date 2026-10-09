from dataclasses import dataclass

STEPS = ("language", "level", "brain", "senses", "home", "trust")
STATUSES = ("done", "skipped")
MAX_NOTE = 120
TRUST_PROFILES = {
    "careful": {"autonomy": "0", "agent_access": "standard"},
    "balanced": {"autonomy": "auto", "agent_access": "standard"},
    "autonomous": {"autonomy": "1", "agent_access": "completo"},
}


@dataclass(frozen=True)
class Mark:
    status: str
    at: float
    note: str = ""

    def as_dict(self) -> dict:
        return {"status": self.status, "at": self.at, "note": self.note}


def restore(raw) -> dict[str, Mark]:
    if not isinstance(raw, dict):
        return {}
    marks = {}
    for step, value in raw.items():
        if step in STEPS and isinstance(value, dict) and value.get("status") in STATUSES:
            marks[step] = Mark(value["status"], float(value.get("at") or 0), str(value.get("note") or "")[:MAX_NOTE])
    return marks


def mark(marks: dict[str, Mark], step, status, note, now: float) -> dict[str, Mark]:
    if step not in STEPS:
        raise ValueError("Passo del Risveglio sconosciuto")
    if status not in STATUSES:
        raise ValueError("Stato del passo non valido")
    if not isinstance(note, str):
        raise ValueError("Nota non valida")
    return {**marks, step: Mark(status, now, note.strip()[:MAX_NOTE])}


def progress(marks: dict[str, Mark]) -> dict:
    finished = [s for s in STEPS if s in marks]
    upcoming = next((s for s in STEPS if s not in marks), "")
    return {"finished": len(finished), "total": len(STEPS), "percent": round(100 * len(finished) / len(STEPS)),
            "next": upcoming, "complete": not upcoming}


def trust_profile(autonomy_mode: str, agent_access: str) -> str:
    for name, profile in TRUST_PROFILES.items():
        if profile == {"autonomy": autonomy_mode, "agent_access": agent_access}:
            return name
    return ""
