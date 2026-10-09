import re
from pathlib import Path

from config import DEMO, STATE_DIR, env_get

from features.actions.common import WORK_DIR
from features.shares import archive

WORK = (STATE_DIR / "srv") if DEMO else WORK_DIR
FILES = archive.path("documenti")
TRASH = STATE_DIR / "cestino"
MODELS = STATE_DIR / "models3d"
FORBIDDEN = ("/proc", "/sys", "/dev", "/boot", "/etc/shadow", "/etc/gshadow", "/etc/sudoers")


ALIASES = {re.sub(r"^\d+\s*", "", name).lower(): kind for kind, name in archive.FOLDERS.items()}
ALIASES.update({name.lower(): kind for kind, name in archive.FOLDERS.items()})
ALIASES.update({kind: kind for kind in archive.FOLDERS})
ALIASES.update({"condivisa": "", "cartella condivisa": ""})


class AccessDenied(Exception):
    pass


def level() -> str:
    value = env_get("ATENA_AGENT_ACCESS", "completo").lower()
    return value if value in ("standard", "completo") else "completo"


def roots() -> list[Path]:
    return [WORK, MODELS]


def inside(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def resolve(raw: str) -> Path:
    text = str(raw or "").strip().strip("\"'")
    if not text:
        raise ValueError("percorso mancante")
    p = Path(text).expanduser()
    if not p.is_absolute():
        p = relative(p)
    p = p.resolve()
    if any(str(p).startswith(f) for f in FORBIDDEN):
        raise AccessDenied(f"{p} è un'area protetta del sistema")
    if level() == "standard" and not any(inside(p, r) for r in roots()):
        raise AccessDenied(f"con l'accesso standard posso lavorare solo in {WORK} e nei modelli 3D")
    return p


def relative(p: Path) -> Path:
    head, rest = p.parts[0].lower().strip(), p.parts[1:]
    if head in ALIASES:
        kind = ALIASES[head]
        return (archive.path(kind) if kind else archive.ROOT).joinpath(*rest)
    if (FILES / p).exists() or not (archive.ROOT / p).exists():
        return FILES / p
    return archive.ROOT / p


def layout() -> str:
    return "; ".join(f"{name} ({archive.DESCRIPTIONS[kind]})" for kind, name in archive.FOLDERS.items())


def trusted(path: Path) -> bool:
    return any(inside(path, r) for r in roots())
