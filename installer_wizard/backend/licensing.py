import re
from dataclasses import asdict, dataclass

from config import env_get

COMMERCIAL_KEY = "ATENA_COMMERCIAL"
UNOFFICIAL_KEY = "ATENA_UNOFFICIAL_SERVICES"
NONCOMMERCIAL_NOTICE = "Licenza solo per uso personale e non commerciale"
UNOFFICIAL_NOTICE = "Usa un servizio non ufficiale: si attiva solo se accetti i termini del servizio, sotto la tua responsabilità"
UNKNOWN_NOTICE = "Licenza sconosciuta: verificala prima di usarlo"


@dataclass(frozen=True)
class License:
    name: str
    url: str
    commercial: bool
    attribution: str = ""
    unofficial: bool = False
    regions: str = ""


APACHE = License("Apache-2.0", "https://www.apache.org/licenses/LICENSE-2.0", True)
MIT = License("MIT", "https://opensource.org/license/mit", True)
QWEN_RESEARCH = License("Qwen Research License", "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE", False)
LLAMA_31 = License("Llama 3.1 Community License", "https://www.llama.com/llama3_1/license/", True, "Built with Llama")
LLAMA_32 = License("Llama 3.2 Community License", "https://www.llama.com/llama3_2/license/", True, "Built with Llama")
LLAMA_32_VISION = License("Llama 3.2 Community License", "https://www.llama.com/llama3_2/license/", True, "Built with Llama",
                          regions="Non concesso a persone residenti o aziende con sede nell'Unione Europea (modelli multimodali Llama 3.2)")
GEMMA = License("Gemma Terms of Use", "https://ai.google.dev/gemma/terms", True, "Soggetto ai Gemma Terms of Use e alla Prohibited Use Policy")
UNKNOWN = License("Sconosciuta", "", False)

MODEL_LICENSES: tuple[tuple[str, License], ...] = (
    (r"^qwen2\.5(-coder)?:3b", QWEN_RESEARCH),
    (r"^qwen2\.5(-coder|vl)?:(0\.5|1\.5|7|14|32)b", APACHE),
    (r"^granite3(\.\d)?(-dense|-moe)?:", APACHE),
    (r"^deepseek-r1:(1\.5|7|14|32)b", APACHE),
    (r"^deepseek-r1:(8|70)b", LLAMA_31),
    (r"^llama3\.1:", LLAMA_31),
    (r"^llama3\.2-vision", LLAMA_32_VISION),
    (r"^llama3\.2:(1|3)b", LLAMA_32),
    (r"^(mistral|mistral-nemo):", APACHE),
    (r"^(phi4|phi3\.5)", MIT),
    (r"^gemma(2|3):", GEMMA),
    (r"^llava:7b", APACHE),
    (r"^nomic-embed-text", APACHE),
    (r"^bge-m3", MIT),
)

COMPONENTS: dict[str, License] = {
    "wakeword": License("CC BY-NC-SA 4.0 (openWakeWord, modelli di base)", "https://github.com/dscripka/openWakeWord#license",
                        False, "openWakeWord di David Scripka"),
    "piper_voices": License("Licenza per singola voce (Piper voices)", "https://huggingface.co/rhasspy/piper-voices", False,
                            "Piper voices di Michael Hansen e dei rispettivi autori dei dataset"),
    "speaker_model": License("CC BY 4.0 (WeSpeaker, VoxCeleb)", "https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md",
                             True, "WeSpeaker ResNet34 addestrato su VoxCeleb (Nagrani et al.)"),
    "shazam": License("Termini di servizio Shazam (API non ufficiale)", "https://www.apple.com/legal/internet-services/shazam/", False,
                      unofficial=True),
    "edge_tts": License("Termini di servizio Microsoft (servizio non ufficiale)", "https://www.microsoft.com/servicesagreement", False,
                        unofficial=True),
}


def _flag(key: str) -> bool:
    return (env_get(key, "0") or "0").strip().lower() in ("1", "true", "yes", "si", "sì", "on")


def commercial_mode() -> bool:
    return _flag(COMMERCIAL_KEY)


def unofficial_accepted() -> bool:
    return _flag(UNOFFICIAL_KEY)


def model_license(name: str) -> License:
    plain = str(name or "").strip().lower()
    return next((lic for pattern, lic in MODEL_LICENSES if re.match(pattern, plain)), UNKNOWN)


def warnings(lic: License) -> list[str]:
    notes = []
    if lic is UNKNOWN:
        notes.append(UNKNOWN_NOTICE)
    elif not lic.commercial:
        notes.append(NONCOMMERCIAL_NOTICE + (": in uso commerciale non è consentito" if commercial_mode() else ""))
    if lic.regions:
        notes.append(lic.regions)
    if lic.unofficial:
        notes.append(UNOFFICIAL_NOTICE)
    return notes


def suggested(lic: License) -> bool:
    return lic is not UNKNOWN and lic.commercial and not lic.unofficial and not lic.regions


def permitted(component: str) -> bool:
    lic = COMPONENTS[component]
    return not lic.unofficial or unofficial_accepted()


def auto_install(component: str) -> bool:
    return COMPONENTS[component].commercial or not commercial_mode()


def describe(lic: License) -> dict:
    return {**asdict(lic), "warnings": warnings(lic), "warning": " · ".join(warnings(lic)), "suggested": suggested(lic)}


def status() -> dict:
    return {"commercial": commercial_mode(), "unofficial": unofficial_accepted(),
            "components": {key: describe(lic) for key, lic in COMPONENTS.items()}}
