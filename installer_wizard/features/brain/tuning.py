import re
from dataclasses import dataclass
from typing import Mapping

TEMPERATURE = (0.0, 1.5)
MAX_TOKENS = (64, 16384)
TIMEOUT = (5, 600)
INSTRUCTIONS_LIMIT = 1200
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TuningError(ValueError):
    pass


@dataclass(frozen=True)
class Tuning:
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: int | None = None
    instructions: str = ""

    @property
    def empty(self) -> bool:
        return self.temperature is None and self.max_tokens is None and self.timeout is None and not self.instructions

    def to_json(self) -> dict:
        return {"temperature": self.temperature, "max_tokens": self.max_tokens, "timeout": self.timeout,
                "instructions": self.instructions}

    def system(self, base: str) -> str:
        if not self.instructions:
            return base
        extra = f"Istruzioni specifiche per questo agente:\n{self.instructions}"
        return f"{base}\n\n{extra}" if base else extra


def _number(raw, bounds: tuple, kind, label: str):
    if raw is None or raw == "":
        return None
    try:
        value = kind(raw)
    except (TypeError, ValueError) as exc:
        raise TuningError(f"{label} non valido") from exc
    if not bounds[0] <= value <= bounds[1]:
        raise TuningError(f"{label} deve essere tra {bounds[0]} e {bounds[1]}")
    return value


def parse(raw: Mapping | None) -> Tuning:
    if not raw:
        return Tuning()
    if not isinstance(raw, Mapping):
        raise TuningError("parametri dell'agente non validi")
    instructions = _CONTROL.sub("", str(raw.get("instructions") or "")).strip()
    if len(instructions) > INSTRUCTIONS_LIMIT:
        raise TuningError(f"istruzioni troppo lunghe (massimo {INSTRUCTIONS_LIMIT} caratteri)")
    return Tuning(
        temperature=_number(raw.get("temperature"), TEMPERATURE, float, "temperatura"),
        max_tokens=_number(raw.get("max_tokens"), MAX_TOKENS, int, "lunghezza massima"),
        timeout=_number(raw.get("timeout"), TIMEOUT, int, "tempo massimo"),
        instructions=instructions,
    )
