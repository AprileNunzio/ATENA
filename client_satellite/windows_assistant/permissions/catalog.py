from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


LEVEL_LABELS = {Level.ALLOW: "Consenti", Level.ASK: "Chiedi ogni volta", Level.DENY: "Mai"}


@dataclass(frozen=True)
class Capability:
    key: str
    group: str
    title: str
    hint: str
    default: Level
    risky: bool = False


CAPABILITIES = (
    Capability("files.folders", "File e cartelle", "Creare cartelle", "Nuove cartelle nelle tue cartelle personali.", Level.ALLOW),
    Capability("files.create", "File e cartelle", "Creare file", "Nuovi documenti, pagine web, codice, script (senza eseguirli).", Level.ALLOW),
    Capability("files.modify", "File e cartelle", "Modificare o sostituire file esistenti",
               "Prima di ogni modifica ATENA salva una copia di sicurezza.", Level.ASK),
    Capability("files.read", "File e cartelle", "Leggere file e cercare", "Leggere documenti, elencare cartelle, cercare file per nome.", Level.ALLOW),
    Capability("files.outside", "File e cartelle", "Lavorare fuori dalle cartelle personali",
               "Dischi e cartelle di sistema. Sconsigliato.", Level.DENY, True),
    Capability("open.files", "Aprire", "Aprire documenti e cartelle", "Con il programma predefinito di Windows.", Level.ALLOW),
    Capability("open.apps", "Aprire", "Avviare applicazioni", "Solo programmi presenti nel menu Start.", Level.ALLOW),
    Capability("open.web", "Aprire", "Aprire siti web", "Solo indirizzi http e https nel browser.", Level.ALLOW),
    Capability("input.type", "Scrivere e desktop", "Scrivere nel programma aperto", "Incolla il testo dove si trova il cursore.", Level.ALLOW),
    Capability("input.clipboard", "Scrivere e desktop", "Usare gli appunti", "Copiare testo negli appunti.", Level.ALLOW),
    Capability("desktop.control", "Scrivere e desktop", "Gestire finestre e tasti",
               "Portare in primo piano, ridurre o ingrandire finestre, premere combinazioni di tasti.", Level.ASK),
    Capability("scripts.run", "Esecuzione", "Eseguire script", "File .ps1, .bat, .cmd, .py nelle cartelle consentite.", Level.ASK, True),
    Capability("shell.powershell", "Esecuzione", "Eseguire comandi PowerShell",
               "Comandi scritti da ATENA: vedrai sempre il comando esatto prima di confermare.", Level.ASK, True),
    Capability("remote.ssh", "Esecuzione", "Comandi SSH su altri computer",
               "Solo con chiavi SSH già configurate e server già conosciuti.", Level.ASK, True),
    Capability("senses.screen", "Sensi", "Guardare lo schermo", "Testo o immagine della finestra su cui lavori, solo quando serve.", Level.ALLOW),
    Capability("senses.webcam", "Sensi", "Usare la webcam", "Una sola foto, solo quando lo chiedi.", Level.ASK),
    Capability("senses.microphone", "Sensi", "Ascolto continuo «Atena»",
               "Se negato, ATENA ascolta solo quando premi i tasti rapidi.", Level.ALLOW),
)

BY_KEY = {c.key: c for c in CAPABILITIES}
GROUPS = tuple(dict.fromkeys(c.group for c in CAPABILITIES))
