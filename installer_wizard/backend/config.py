import json
import os
import re
import tempfile
from contextvars import ContextVar
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR.parent
WEB_DIR = APP_DIR / "web"
FEATURES_DIR = APP_DIR / "features"
WIDGETS_DIR = APP_DIR / "widgets"
SKILLS_DIR = APP_DIR / "skills"

DEMO = os.environ.get("ATENA_DEMO") == "1"

ATENA_DIR = Path(os.environ.get("ATENA_DIR", BACKEND_DIR.parents[1] if DEMO else "/opt/Atena"))
_ROOT = Path(tempfile.gettempdir()) / "atena-demo" if DEMO else Path("/")
ETC_DIR = _ROOT / "etc/atena"
STATE_DIR = _ROOT / "var/lib/atena"
LOG_DIR = _ROOT / "var/log/atena"
ENV_FILE = ETC_DIR / "atena.env"
STEPS_DIR = ATENA_DIR / "scripts/os/steps"
HEAL_SCRIPT = ATENA_DIR / "scripts/os/heal.sh"

PUBLIC_PORT = int(os.environ.get("ATENA_PUBLIC_PORT", 8000 if DEMO else 80))
ADMIN_PORT = int(os.environ.get("ATENA_ADMIN_PORT", 8001 if DEMO else 8080))
CORE_URL = os.environ.get("ATENA_CORE_URL", "http://127.0.0.1:8443")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

VERSION = "4.1.33"
UI_LANGUAGES = {"it": "Italiano", "en": "English", "fr": "Français", "es": "Español", "de": "Deutsch", "pt": "Português",
                "nl": "Nederlands", "pl": "Polski", "ro": "Română", "ru": "Русский", "uk": "Українська", "el": "Ελληνικά",
                "tr": "Türkçe", "ar": "العربية", "he": "עברית", "fa": "فارسی", "zh": "中文", "ja": "日本語", "ko": "한국어",
                "hi": "हिन्दी", "sv": "Svenska", "da": "Dansk", "nb": "Norsk", "fi": "Suomi", "cs": "Čeština", "hu": "Magyar",
                "sq": "Shqip", "hr": "Hrvatski", "bg": "Български", "vi": "Tiếng Việt", "th": "ไทย", "id": "Bahasa Indonesia",
                "ms": "Bahasa Melayu"}

for _d in (ETC_DIR, STATE_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

EDITABLE_KEYS = {
    "ATENA_LLM_MODEL": "Cervello potente: modello per il ragionamento (Ollama; vuoto = automatico)",
    "ATENA_LLM_FAST_MODEL": "Cervello veloce: modello per la conversazione (Ollama; vuoto = automatico)",
    "ATENA_LLM_ROUTING": "Instradamento tra cervello veloce e potente (auto, 1 = sempre, 0 = un solo cervello)",
    "ATENA_LLM_CHAT_ORDER": "Priorità dei modelli per la conversazione (separati da virgola; vuoto = automatico)",
    "ATENA_LLM_DEEP_ORDER": "Priorità dei modelli per il ragionamento (separati da virgola; vuoto = automatico)",
    "ATENA_EMBED_MODEL": "Modello di embedding (Ollama)",
    "ATENA_NETGUARD": "Analisi del traffico per il firewall (1 = attiva, 0 = spenta)",
    "ATENA_NETGUARD_INTERFACES": "Interfacce analizzate dal firewall (es. eth0, wlan0; vuoto = tutte quelle ethernet e wifi)",
    "ATENA_GATEWAY_IP": "IP del router di casa, che il firewall non bloccherà mai",
    "ATENA_VPN": "Strumenti VPN WireGuard, OpenVPN e IPsec (1 = installati, 0 = no)",
    "ATENA_OLLAMA_URL": "Server Ollama (vuoto = locale; es. http://192.168.1.50:11434 per usare un altro server)",
    "ATENA_ASSISTANT_NAME": "Nome dell'assistente (predefinito A.T.E.N.A.)",
    "ATENA_USER_NAME": "Nome dell'utente principale (come Atena ti chiama)",
    "ATENA_UI_LANG": "Lingua dell'interfaccia del display e del pannello (it, en, fr)",
    "ATENA_LOCATION": "Posizione predefinita (nome; si imposta meglio da Audio e posizione)",
    "ATENA_LOCATION_MODE": "Posizione: auto (display/Wi-Fi più precisi) o fixed (sempre la predefinita)",
    "ATENA_LOCATION_LAT": "Latitudine della posizione predefinita",
    "ATENA_LOCATION_LON": "Longitudine della posizione predefinita",
    "ATENA_MUSIC_ID": "Riconoscimento della musica in ascolto (1/0; invia 10 s di audio a Shazam, servizio non ufficiale: serve anche ATENA_UNOFFICIAL_SERVICES=1)",
    "ATENA_STUDY_FINETUNE": "Consolidamento dello studio nei pesi con Soup (auto = deciso dall'hardware, 1 = sempre, 0 = mai)",
    "ATENA_STUDY_BASE_MODEL": "Modello base per Soup (Hugging Face, es. Qwen/Qwen2.5-1.5B-Instruct)",
    "ATENA_VOICE": "Voce principale (es. if_sara, im_nicola, it_IT-serena-high; si gestisce da Voci)",
    "ATENA_VOICE_ORDER": "Priorità delle voci (separate da virgola; si gestisce meglio da Voci)",
    "ATENA_VOICE_SPEED": "Velocità della voce (0.6 - 1.6)",
    "ATENA_CAMERAS": "Telecamere e registrazione ad anello (1/0, spento di default)",
    "ATENA_ADDRESSEE_THRESHOLD": "Soglia per decidere se gli stai parlando (0.2 - 0.95)",
    "ATENA_ADDRESSEE_ALONE": "Fiducia aggiuntiva quando sei solo nella stanza (0 - 1)",
    "ATENA_VOICE_PITCH": "Tono della voce in semitoni (-6 grave, +6 acuto)",
    "ATENA_VOICE_VOLUME": "Volume della voce (0.4 - 2.0)",
    "ATENA_VOICE_LANG": "Voce preferita per ogni lingua (es. en:am_michael,de:de_DE-thorsten-medium; si gestisce da Voci)",
    "ATENA_VOICE_ONLINE": "Voci neurali online di Edge (1 = sì, 0 = mai; servizio non ufficiale: serve anche ATENA_UNOFFICIAL_SERVICES=1)",
    "ATENA_VOICE_AUTO_DOWNLOAD": "Scarica da solo la voce di una lingua nuova quando serve (1/0)",
    "ATENA_EAR_MULTILANG": "Riconosce la lingua in cui parli (1/0; 0 = ascolta solo l'italiano)",
    "ATENA_EAR_MODE": "Modalità di ascolto: offline (locale privato, default), online (cloud alta precisione) o hybrid",
    "ATENA_ONLINE_STT_PROVIDER": "Fornitore STT online (deepgram, groq, openai, gemini)",
    "ATENA_ONLINE_STT_KEY": "Chiave API per il servizio STT online",
    "ATENA_EAR_AUTO_FOLLOWUP": "Finestra di ascolto continuo dopo una risposta (secondi, default 8)",
    "ATENA_VOICEPRINT_ENFORCE": "Filtro anti-TV ed estranei: rispondi solo alle voci registrate (1/0)",
    "ATENA_EAR_ENHANCE_ENGINE": "Motore di pulizia audio e dereverberazione (auto, deepfilternet, spectral)",
    "ATENA_VISION": "Webcam e riconoscimento facciale (1/0)",
    "ATENA_EAR": "Ascolto vocale con parola \"Atena\" (1/0)",
    "ATENA_STT_MODEL": "Modello di ascolto offline (vuoto = automatico; base, small, medium, large-v3-turbo)",
    "ATENA_EAR_MAX_GAIN": "Amplificazione massima del microfono per il campo lontano (2 - 80)",
    "ATENA_EAR_TARGET_RMS": "Livello vocale obiettivo dell'autolivellamento (0.03 - 0.2)",
    "ATENA_AVATAR": "Aspetto dell'assistente (auto = in base al dispositivo, full = ologramma 3D con volto, light = nucleo leggero)",
    "ATENA_FACE_COLOR": "Colore dell'ologramma (colore, es. #29e0ff)",
    "ATENA_AUTO_UPDATE": "Aggiornamenti automatici (1/0)",
    "ATENA_UPDATE_INTERVAL_MIN": "Controllo aggiornamenti ogni N minuti (default 5)",
    "ATENA_UPDATE_BRANCH": "Ramo GitHub",
    "ATENA_KIOSK": "Display kiosk (1/0)",
    "GEMINI_API_KEY": "API key Google Gemini (fallback)",
    "ANTHROPIC_API_KEY": "API key Anthropic Claude (fallback)",
    "ATENA_TELEGRAM_TOKEN": "Token del bot Telegram (da @BotFather)",
    "ATENA_TELEGRAM": "Bot Telegram attivo (1/0)",
    "ATENA_NETWORK": "Esploratore della rete locale (1/0)",
    "ATENA_SPOTIFY": "Spotify attivo (1/0)",
    "ATENA_SPOTIFY_CLIENT_ID": "Spotify: Client ID dell'app (developer.spotify.com)",
    "ATENA_SPOTIFY_CLIENT_SECRET": "Spotify: Client Secret dell'app",
    "ATENA_SPOTIFY_WHEN": "Spotify: quando mostrare il brano (present = se ti vede, always = sempre)",
    "ATENA_GOOGLE": "Google: connettori Calendar, Gmail, Tasks, Contatti, Drive, Keep attivi (1/0)",
    "ATENA_GOOGLE_CLIENT_ID": "Google: Client ID OAuth (App desktop, console.cloud.google.com)",
    "ATENA_GOOGLE_CLIENT_SECRET": "Google: Client Secret OAuth",
    "ATENA_GOOGLE_SERVICES": "Google: servizi da collegare (calendar,gmail,tasks,contacts,drive,keep)",
    "ATENA_GOOGLE_REMIND_MIN": "Google: avviso sul display N minuti prima di ogni appuntamento (0 = mai)",
    "ATENA_MAPS": "Maps: indicazioni, tempi e avvisi di viaggio (1/0)",
    "ATENA_MAPS_API_KEY": "Maps: chiave Google Maps Platform (Routes API) per traffico e mezzi; vuota = OpenStreetMap",
    "ATENA_MAPS_MODE": "Maps: mezzo predefinito (drive, walk, bike, transit, moto)",
    "ATENA_MAPS_EVENT_HOURS": "Maps: ore in anticipo in cui guardare gli appuntamenti con un luogo (default 4)",
    "ATENA_SKILLS": "Algoritmi riutilizzabili per calcoli e conversioni (1/0)",
    "ATENA_SKILLS_GENERATE": "Atena scrive da sola nuovi algoritmi quando servono (1/0)",
    "HOME_ASSISTANT_URL": "URL Home Assistant",
    "HOME_ASSISTANT_TOKEN": "Token Home Assistant",
    "HOME_ASSISTANT_VERIFY_SSL": "Home Assistant: verifica il certificato HTTPS (1/0; 0 per certificati autofirmati)",
    "ATENA_HOME_ASSISTANT": "Casa: collegamento a Home Assistant attivo (1/0)",
    "ATENA_HOME_ROOM": "Casa: stanza in cui si trova Atena (nome dell'area di Home Assistant)",
    "ATENA_HOME_MOTION_MIN": "Casa: minuti dopo l'ultimo movimento in cui una stanza resta occupata (default 5)",
    "ATENA_HOME_CONFIRM": "Casa: chiedi conferma per serrature, allarme, cancelli e garage (1/0)",
    "ATENA_HANDS": "Comandi con le mani davanti alla webcam (auto = solo se la GPU del display li regge, 1 = sempre, 0 = mai)",
    "ATENA_HANDS_FPS": "Comandi con le mani: analisi al secondo con una mano in vista (10/20/30)",
    "ATENA_HANDS_COUNT": "Comandi con le mani: mani riconosciute (1/2)",
    "ATENA_HANDS_MAX_MS": "Comandi con le mani: in automatico si spengono se un'analisi supera questi millisecondi (30/50/90)",
    "ATENA_AUTOMATIONS": "Automazioni a più stadi: inneschi, condizioni, azioni, rami, attese, webhook (1/0)",
    "ATENA_SOUNDS": "Suoni ed effetti (1/0)",
    "ATENA_SOUNDS_VOLUME": "Suoni: volume degli effetti 0-100",
    "ATENA_SOUNDS_THEME": "Suoni: tema (atena, soft, classic)",
    "ATENA_SOUNDS_FEEDBACK": "Suoni di attivazione e richiesta (1/0)",
    "ATENA_SOUNDS_THINKING": "Suono mentre pensa ed elabora (1/0)",
    "ATENA_SOUNDS_NOTIFY": "Suoni di notifica (1/0)",
    "ATENA_SOUNDS_AMBIENT": "Sottofondo (none, reactor, space, rain, ocean, lab)",
    "ATENA_SOUNDS_AMBIENT_VOLUME": "Volume del sottofondo 0-100",
    "ATENA_QUIET_MODE": "Orari di silenzio: soft (attenua), mute (solo allarmi), off",
    "ATENA_QUIET_START": "Silenzio dalle HH:MM",
    "ATENA_QUIET_END": "Silenzio fino alle HH:MM",
    "ATENA_QUIET_DAYS": "Notti di silenzio: all, weekdays, weekend",
    "ATENA_QUIET_VOICE": "Volume della voce in silenzio 0-100",
    "ATENA_QUIET_EFFECTS": "Volume degli effetti in silenzio attenuato 0-100",
    "ATENA_SELFTEST": "Collaudo notturno e dopo ogni aggiornamento (1/0)",
    "ATENA_SELFTEST_AT": "Ora del collaudo notturno HH:MM",
    "ATENA_SELFTEST_ROLLBACK": "Torna alla versione precedente se un aggiornamento rompe una funzione essenziale (1/0)",
    "ATENA_UPDATE_REQUIRE_CI": "Installa solo versioni con i test superati su GitHub (1/0)",
    "ATENA_HABITS": "Abitudini: osserva la casa e propone automazioni (1/0)",
    "ATENA_HABITS_CONFIDENCE": "Abitudini: regolarità minima per proporre (0.6, 0.7, 0.8)",
    "ATENA_HABITS_ASK": "Abitudini: proposte a voce (1/0)",
    "ATENA_HABITS_ANOMALIES": "Avvisi di situazioni insolite con casa vuota (1/0)",
    "ATENA_VAULT": "Memoria in file leggibili e diario giornaliero (1/0)",
    "ATENA_VAULT_DIR": "Cartella della memoria in chiaro (vuoto = /var/lib/atena/memoria, solo sul server)",
    "ATENA_GPU_DRIVER": "Driver video del display: auto (NVIDIA ufficiale se adatto), nouveau (libero)",
    "ATENA_GPU_DRIVER_REBOOT": "Riavvio per attivare il driver video: night (alle 04:15) o now",
    "ATENA_SHARES": "Cartella condivisa Samba «condivisa» con le creazioni di Atena, protetta da password (1/0)",
    "ATENA_SMB_PASSWORD": "Password dell'utente atena-share per la cartella condivisa",
    "ATENA_AUTONOMY": "Autonomia: compiti programmati, autopilota (diagnosi, studio, riepilogo serale) e approvazioni (1/0)",
    "ATENA_WELCOME": "Quando ti riconosce mostra meteo, promemoria e riepilogo Google nei widget (1/0)",
    "ATENA_AGENT": "Agente con strumenti: file, widget, ologramma, 3D, email, SMB, terminale (1/0)",
    "ATENA_AGENT_ACCESS": "Accesso dell'agente (completo = tutto il server con conferma per le azioni delicate, standard = solo /srv/atena e modelli 3D)",
    "ATENA_SMTP_HOST": "Email in uscita: server SMTP (es. smtp.gmail.com; vuoto = usa Gmail collegato)",
    "ATENA_SMTP_PORT": "Email in uscita: porta SMTP (587 STARTTLS, 465 SSL)",
    "ATENA_SMTP_USER": "Email in uscita: utente SMTP",
    "ATENA_SMTP_PASSWORD": "Email in uscita: password SMTP (per Gmail una password per le app)",
    "ATENA_SMTP_FROM": "Email in uscita: mittente (vuoto = utente SMTP)",
    "ATENA_DOCUMENTS": "Documenti Office e LibreOffice: Word, Excel, PowerPoint, ODT, ODS, ODP, PDF e progetti (1/0)",
    "ATENA_COMMERCIAL": "Uso commerciale (1 = Atena è usata in un'attività: non installa da sola componenti con licenza non commerciale e li segnala con un avviso; 0 = uso personale)",
    "ATENA_UNOFFICIAL_SERVICES": "Servizi non ufficiali (riconoscimento Shazam, voci online di Edge): 1 = li attivo accettandone i termini sotto la mia responsabilità, 0 = mai",
    "ATENA_3D_CONVERT": "Conversione 3D sul server: Blender per BLEND/USD/USDZ e LibreDWG per DWG (auto = se c'è spazio, 1 = sì, 0 = no)",
}
SECRET_KEYS = {"ATENA_SECRET_KEY", "ATENA_SMB_PASSWORD", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "HOME_ASSISTANT_TOKEN", "ATENA_TELEGRAM_TOKEN", "ATENA_SMTP_PASSWORD",
               "ATENA_SPOTIFY_CLIENT_SECRET", "ATENA_SPOTIFY_REFRESH_TOKEN",
               "ATENA_GOOGLE_CLIENT_SECRET", "ATENA_GOOGLE_REFRESH_TOKEN", "ATENA_MAPS_API_KEY",
               "ATENA_ONLINE_STT_KEY", "ATENA_MUSIC_APP_PASSWORD", "ATENA_CLOUD_KEY"}
SECRET_RE = re.compile(r"(KEY|TOKEN|PASSWORD|PASSWD|SECRET|PASSPHRASE|CREDENTIALS?|COOKIE)(_|$)")


def is_secret(key: str) -> bool:
    return key in SECRET_KEYS or bool(SECRET_RE.search(key))
_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


NODE = ContextVar("atena_node", default="")
NODE_FIXED = {"ATENA_AUTO_UPDATE", "ATENA_UPDATE_INTERVAL_MIN", "ATENA_UPDATE_BRANCH", "ATENA_GOOGLE_CLIENT_ID",
              "ATENA_SPOTIFY_CLIENT_ID", "HOME_ASSISTANT_URL", "ATENA_TELEGRAM", "ATENA_AGENT_ACCESS"}
_nodes_cache = {"mtime": -1.0, "data": {}}


def node_keys() -> list[str]:
    return [k for k in EDITABLE_KEYS if not is_secret(k) and k not in NODE_FIXED]


def node_overrides(node_id: str) -> dict:
    path = STATE_DIR / "nodes.json"
    try:
        mtime = path.stat().st_mtime
        if mtime != _nodes_cache["mtime"]:
            _nodes_cache.update(mtime=mtime, data=json.loads(path.read_text(encoding="utf-8")).get("nodes", {}))
    except (OSError, ValueError):
        return {}
    allowed = set(node_keys())
    return {k: v for k, v in (_nodes_cache["data"].get(node_id, {}).get("settings") or {}).items() if k in allowed}


def read_env() -> dict:
    env = read_global_env()
    node = NODE.get()
    if node:
        env.update(node_overrides(node))
    return env


def read_global_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"')
    return env


_ollama_cache: dict = {}


def ollama_url() -> str:
    import time
    node = NODE.get()
    at, url = _ollama_cache.get(node, (0.0, OLLAMA_URL))
    if time.time() - at > 5:
        custom = read_env().get("ATENA_OLLAMA_URL", "").strip().rstrip("/")
        if custom and not custom.startswith(("http://", "https://")):
            custom = f"http://{custom}"
        if custom and not re.search(r":\d+$", custom.split("//", 1)[1]):
            custom += ":11434"
        url = custom or OLLAMA_URL
        _ollama_cache[node] = (time.time(), url)
    return url


def ollama_remote() -> bool:
    host = ollama_url().split("//", 1)[-1].split(":", 1)[0]
    return host not in ("127.0.0.1", "localhost", "::1", "")


def write_env(updates: dict) -> None:
    for key, value in updates.items():
        if not _KEY_RE.match(key) or "\n" in str(value):
            raise ValueError(f"Chiave o valore non valido: {key}")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    pending = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in pending:
            value = pending.pop(key)
            if value != "":
                out.append(f"{key}={value}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in pending.items() if v != "")
    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_FILE)


def env_get(key: str, default: str = "") -> str:
    return read_env().get(key, default)


def kiosk_log() -> Path:
    user = env_get("ATENA_KIOSK_USER", "atena-kiosk")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        user = "atena-kiosk"
    return Path("/home") / user / ".cache" / "atena-kiosk.log"
