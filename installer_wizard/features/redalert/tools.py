from features.agent.registry import tool
from features.redalert.service import redalert


@tool("red_alert", "allarme rosso: fa lampeggiare di rosso tutte le luci di casa e ripete un messaggio urgente su tutti i "
      "Chromecast", {"message": "messaggio urgente da dire", "seconds": "durata in secondi (facoltativa)"}, confirm=True,
      agent="redalert")
async def red_alert(message: str, seconds: int = 0) -> str:
    if not redalert.trigger(str(message)[:400], max(10, min(600, int(seconds or 0))) if seconds else None):
        return "l'allarme rosso è disattivato nelle funzionalità"
    return "allarme rosso attivato: luci rosse e messaggio sui Chromecast"


@tool("stop_red_alert", "ferma l'allarme rosso e rimette le luci come prima", {}, agent="redalert")
async def stop_red_alert() -> str:
    redalert.stop()
    return "allarme rosso fermato"
