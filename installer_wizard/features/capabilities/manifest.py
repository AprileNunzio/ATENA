from config import env_get
from features.agent import agent as agent_module
from features.agent import registry
from features.agent.paths import level
from features.team import roster
from features.team.board import board

VOICE = {
    "Musica": ["metti AC DC", "suona Back In Black", "metti l'album Thriller", "metti la playlist Palestra", "metti del rock sul Chromecast del salotto",
               "pausa", "riprendi", "prossima canzone", "canzone precedente", "alza il volume", "volume al 40 per cento", "mi piace questa canzone", "ferma la musica"],
    "Telecamere": ["apri la webcam", "apri la telecamera ingresso", "apri tutte le telecamere", "a tutto schermo", "schermo normale", "chiudi la telecamera", "cosa vedi"],
    "Lavagna": ["apri la lavagna a tutto schermo", "calcola 12 per 3 più 4 alla lavagna", "risolvi 2x + 3 = 11", "spiegami la fotosintesi alla lavagna", "controlla cosa ho scritto", "scrivi alla lavagna ...", "annulla", "cancella la lavagna", "chiudi la lavagna"],
    "Widget": ["apri il widget meteo", "chiudi il widget", "sposta il widget sul secondo schermo"],
}
DEVICES = "Dispositivi di rete: Chromecast e altoparlanti DLNA vengono trovati da soli; la musica parte su quello nominato («su salotto») o su quello già attivo."
PRIVACY = "I widget con dati personali si chiudono da soli quando la persona si allontana e dopo 30 secondi se richiesti a voce."


def enabled() -> bool:
    return env_get("ATENA_CAPABILITIES", "1") != "0"


def tools() -> list[dict]:
    if not agent_module.MODULES:
        return []
    return [{"name": t["name"], "description": t["description"], "args": t["args"], "needs_confirmation": bool(t["confirm"])}
            for t in registry.available(level())]


def voice_lines() -> list[str]:
    return [f"{area}: " + "; ".join(f"«{p}»" for p in phrases) for area, phrases in VOICE.items()]


def summary() -> str:
    return ("COSA SAI FARE (le azioni le eseguono gli agenti di Atena, non tu: se il signore le chiede, indicagli la frase giusta).\n"
            + "\n".join(voice_lines()) + f"\n{DEVICES}\n{PRIVACY}\n"
            "LA SQUADRA: ogni funzionalità è un agente indipendente con una priorità (più alta = passa avanti); gli agenti si vedono "
            "a vicenda e si passano i compiti (p = priorità). Elenco:\n" + roster.team_text(True) + "\n" + board.digest())


def document() -> dict:
    return {"summary": summary(), "voice": VOICE, "tools": tools(), "notes": [DEVICES, PRIVACY], "team": roster.document()}
