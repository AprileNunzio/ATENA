import asyncio
import re

from state import store

from features.actions.common import sh


async def _apt_upgradable() -> tuple[list[str], str]:
    code, out = await sh("apt-get", "update", "-qq", timeout=180)
    note = "" if code == 0 else "(elenco dei pacchetti non aggiornato: repository non raggiungibili)"
    _, sim = await sh("apt-get", "-s", "-o", "Debug::NoLocking=1", "dist-upgrade", timeout=120)
    pkgs = [ln.split()[1] for ln in sim.splitlines() if ln.startswith("Inst ")]
    return pkgs, note


async def updates_action(text: str) -> tuple[str, dict]:
    import updater

    install = bool(
        re.search(
            r"\b(installa|applica|esegui|fai|procedi|aggiorna(ti|rti)?\s+(ora|adesso|tutto|il sistema))\b", text, re.I
        )
    ) and not re.search(r"\b(controlla|verifica|ci sono|c'?[èe]|esistono|disponibil)\b", text, re.I)
    info, (pkgs, note) = await asyncio.gather(updater.check(), _apt_upgradable())
    atena_new = bool(info.get("available"))
    items = [
        {
            "label": "Atena",
            "value": (
                f"{(info.get('local_rev') or '?')[:7]} → {(info.get('remote_rev') or '?')[:7]}"
                if atena_new
                else f"aggiornato ({(info.get('local_rev') or '?')[:7]})"
            ),
            "status": "warn" if atena_new else "ok",
        }
    ]
    items += [{"label": p, "value": "aggiornabile", "status": "warn"} for p in pkgs[:30]]
    if install and (pkgs or atena_new):
        if pkgs:
            asyncio.get_running_loop().create_task(_apt_upgrade())
        if atena_new:
            asyncio.get_running_loop().create_task(updater.apply("richiesto a voce"))
        speech = f"Avvio l'installazione: {len(pkgs)} pacchetti di sistema" if pkgs else "Avvio l'aggiornamento"
        speech += (
            " e la nuova versione di Atena; mi riavvierò da sola e verificherò che tutto funzioni."
            if atena_new
            else ". Ti avviso quando ho finito."
        )
    else:
        parts = [
            f"Atena ha un aggiornamento disponibile ({len(info.get('changelog') or [])} modifiche)"
            if atena_new
            else "Atena è alla versione più recente"
        ]
        parts.append(
            f"ci sono {len(pkgs)} pacchetti di sistema da aggiornare, tra cui {', '.join(pkgs[:4])}"
            if pkgs
            else "il sistema operativo è aggiornato"
        )
        speech = parts[0] + " e " + parts[1] + "."
        if pkgs or atena_new:
            speech += " Dimmi «installa gli aggiornamenti» e procedo."
        if note:
            speech += " " + note
    return speech, {
        "mode": "focus",
        "title": "Aggiornamenti",
        "subtitle": "Atena e sistema operativo",
        "panels": [{"type": "list", "title": f"Da aggiornare ({len(pkgs) + atena_new})", "items": items}],
    }


async def _apt_upgrade() -> None:
    store.event("INFO", "Installazione degli aggiornamenti di sistema avviata", "actions")
    code, out = await sh(
        "env",
        "DEBIAN_FRONTEND=noninteractive",
        "apt-get",
        "-y",
        "-o",
        "Dpkg::Options::=--force-confdold",
        "dist-upgrade",
        timeout=3600,
    )
    store.event(
        "INFO" if code == 0 else "ERROR",
        "Aggiornamenti di sistema installati" if code == 0 else f"Aggiornamento non riuscito: {out[-200:]}",
        "actions",
    )
