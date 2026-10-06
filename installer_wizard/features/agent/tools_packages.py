import packages
from features.agent.registry import tool

IDS = ", ".join(p.id for p in packages.PACKAGES if p.id != "brain_models")


def _find(name: str) -> packages.Package:
    key = str(name or "").strip().lower()
    for pkg in packages.PACKAGES:
        if pkg.id != "brain_models" and key in (pkg.id, pkg.title.lower()):
            return pkg
    raise ValueError(f"pacchetto sconosciuto: scegli tra {IDS}")


def _changes(args: dict) -> bool:
    return args.get("action") in ("install", "remove")


@tool("packages", "elenca, installa in background o rimuove i pacchetti di Atena (voce, ascolto, visione, documenti Office, ecc.)",
      {"action": "list, install o remove", "package": f"uno tra {IDS}"}, confirm=_changes, full_only=True)
async def manage(action: str = "list", package: str = "") -> str:
    if action == "list":
        rows = [f"- {p['id']}: {p['title']}, {p['size_gb']} GB, {p['state']}" for p in packages.catalog()]
        return f"cervello: {packages.brain_mode()}\n" + "\n".join(rows)
    if action not in ("install", "remove"):
        raise ValueError("azione non valida: list, install o remove")
    from settings import apply_config
    pkg = _find(package)
    on = action == "install"
    if on and packages.state(pkg) in ("installed", "installing", "queued"):
        return f"{pkg.title} è già {packages.state(pkg)}"
    try:
        updates = packages.request_updates(pkg.id, on)
    except KeyError:
        return f"{pkg.title} non si può rimuovere"
    steps = await apply_config(updates, "chat", list(pkg.steps))
    if not on:
        return f"{pkg.title} disattivato"
    return f"installazione di {pkg.title} ({pkg.size_gb} GB) avviata in background: {', '.join(steps) or 'nessuno step'}"
