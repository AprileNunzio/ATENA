import re
from dataclasses import dataclass

_FAST = re.compile(r"mini|flash|haiku|small|nano|lite|fast|instant|8b|3b|1\.5b", re.I)
MAX_PER_SOURCE = 2


@dataclass(frozen=True)
class Preset:
    id: str
    icon: str
    label: str
    hint: str
    scope: str
    sources: tuple[str, ...]


PRESETS: tuple[Preset, ...] = (
    Preset("auto", "✨", "Automatico", "Atena sceglie da sola in base all'hardware.", "anywhere", ()),
    Preset("private", "🔒", "Privato", "Solo modelli in casa: nessun dato esce dalla rete.", "home", ("local", "servers")),
    Preset("balanced", "⚖️", "Bilanciato", "Prima in casa; il cloud solo se la casa non risponde.", "home_first",
           ("local", "servers", "cloud")),
    Preset("smart", "🚀", "Massima intelligenza", "Prima il cloud più capace, la casa come riserva.", "anywhere",
           ("cloud", "local", "servers")),
    Preset("cloud", "☁️", "Solo cloud", "Solo servizi cloud collegati, niente modelli locali.", "anywhere", ("cloud",)),
)
BY_ID = {p.id: p for p in PRESETS}


class PresetError(ValueError):
    pass


def _local(cat: dict, fast: bool) -> list[str]:
    rows = [m for m in cat["local"]["models"] if m["installed"]]
    rows.sort(key=lambda m: m["size_gb"] if m["size_gb"] is not None else 5.0, reverse=not fast)
    return [m["ref"] for m in rows[:MAX_PER_SOURCE]]


def _servers(cat: dict, fast: bool) -> list[str]:
    picks = []
    for server in (s for s in cat["servers"] if s["online"] and s["models"]):
        refs = [m["ref"] for m in server["models"]]
        quick = [r for r in refs if _FAST.search(r)]
        picks.append((quick or refs)[0] if fast else refs[0])
    return picks[:MAX_PER_SOURCE]


def _cloud(cat: dict, fast: bool) -> list[str]:
    picks = []
    for provider in cat["cloud"]:
        refs = [m["ref"] for m in provider["models"]]
        default = next((r for r in refs if r.endswith("/" + provider["default"])), refs[0] if refs else "")
        quick = [r for r in refs if _FAST.search(r.rsplit("/", 1)[-1])]
        choice = (quick[0] if quick else default) if fast else default
        if choice:
            picks.append(choice)
    return picks[:MAX_PER_SOURCE]


def plan(preset_id: str, role_id: str, cat: dict) -> tuple[list[str], str]:
    preset = BY_ID.get(preset_id)
    if not preset:
        raise PresetError("Profilo sconosciuto")
    if preset.id == "auto":
        return [], preset.scope
    fast = role_id == "chat"
    pickers = {"local": _local, "servers": _servers, "cloud": _cloud}
    order = list(dict.fromkeys(ref for source in preset.sources for ref in pickers[source](cat, fast)))
    if not order:
        need = "un servizio cloud collegato" if preset.sources == ("cloud",) else "almeno un modello installato o un server in rete"
        raise PresetError(f"Per il profilo «{preset.label}» serve {need}")
    return order, preset.scope


def clean_profile(value: str | None, custom: bool) -> str:
    if value in BY_ID or value == "custom":
        return value
    return "custom" if custom else "auto"
