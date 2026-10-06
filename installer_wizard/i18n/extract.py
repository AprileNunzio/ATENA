import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTRS = ("placeholder", "title", "aria-label", "alt", "data-confirm")
SKIP_TAGS = {"script", "style", "code", "pre", "svg", "math"}
WORDY = re.compile(r"[A-Za-zÀ-ÿ]{2,}")
ITALIAN_HINT = re.compile(r"[àèéìòù]|\b(il|la|le|lo|gli|di|da|del|della|delle|un|una|non|per|con|che|nessun\w*|salva|annulla|aggiungi|elimina|"
                          r"rimuovi|chiudi|apri|carica\w*|impostazion\w*|stato|attiv\w*|spent\w*|errore|nome|tipo|cerca|aggiorna|"
                          r"modifica|conferma|sicuro|oggi|ieri|minuti|ore|giorni|sì|no|nuov\w*|tutt\w*|ultim\w*|prov\w*|lingua|"
                          r"utente|password|scegli|seleziona|invia|ricevi|telecamer\w*|stampant\w*|abitudin\w*|automazion\w*|"
                          r"persone|casa|luce|luci|musica|voce|ascolto|cervello|modell\w*|aggiornament\w*|funzionalit\w*)\b", re.I)
CODE_LIKE = re.compile(r"^[\w.\-/#:?=&%{}\[\]()$@*+|\\<>!~^,;'\"`]+$|^(https?:|/api/|\.|#[\w-]+$)|[{};=]{2,}|=>|\bfunction\b|"
                       r"^\s*[\w-]+\s*:\s*[\w#-]+\s*;?\s*$")
LITERAL = re.compile(r"`((?:\\.|[^`\\])*)`|\"((?:\\.|[^\"\\\n])*)\"|'((?:\\.|[^'\\\n])*)'")
TAGTEXT = re.compile(r">([^<>]+)<")
INTERP = re.compile(r"\$\{(?:[^{}]|\{[^{}]*\})*\}")
ATTR_IN_TEMPLATE = re.compile(r"\b(?:placeholder|title|aria-label|alt)=\"([^\"$]*(?:\$\{[^}]*\}[^\"$]*)*)\"")


FRAGMENT = re.compile(r"[{}]\s*[\"'`]|[\"'`]\s*[{}]|\$\{|\b(?:esc|join|map|fmt|A\.t|filter|replace|slice)\(|=>|\?\.|\s\?\s|"
                      r"\b(?:class|style|data-[\w-]+|href|src)=|\bsize-|\bw-\{|^[:;,)\]}]|[(\[{]$|^\W+$")


def normal(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


LABEL_WORD = re.compile(r"^[A-ZÀ-Ý][a-zà-ÿ]{2,}$")
SKIP_WORDS = {"Atena", "Telegram", "Spotify", "Google", "Ollama", "Chromecast", "Bluetooth", "Docker", "Kokoro", "Piper", "Samba",
              "Linux", "Windows", "Moonraker", "Klipper", "Whisper", "Deepgram", "Groq", "Gemini", "Claude", "Auto", "Maps", "Home",
              "Display", "Desktop", "Shazam", "Subsonic", "Thermostat", "Spectrum", "Clipboard", "Tasks", "Containers", "Temperature"}


def visible(text: str) -> bool:
    text = normal(text)
    if LABEL_WORD.match(text):
        return text not in SKIP_WORDS
    if len(text) < 2 or not WORDY.search(text) or CODE_LIKE.search(text) or FRAGMENT.search(text):
        return False
    if re.fullmatch(r"[\W\d_]*\w{1,3}[\W\d_]*", text) and not ITALIAN_HINT.search(text):
        return False
    return bool(ITALIAN_HINT.search(text)) or (" " in text and not re.search(r"[A-Z_]{4,}|\bfa-|\bbtn\b|class=", text))


class HtmlStrings(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in ("br", "img", "input", "meta", "link", "hr", "source"):
            self.stack.append(tag)
        for name, value in attrs:
            if name in ATTRS and value and visible(value):
                self.found.append(normal(value))

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        if not any(t in SKIP_TAGS for t in self.stack) and visible(data):
            self.found.append(normal(data))


def from_html(text: str) -> list[str]:
    parser = HtmlStrings()
    parser.feed(text)
    return parser.found


def placeholders(text: str) -> str:
    counter = iter(range(100))
    return INTERP.sub(lambda m: "{" + str(next(counter)) + "}", text)


def from_js(text: str) -> list[str]:
    found: list[str] = []
    for m in LITERAL.finditer(text):
        raw = next(g for g in m.groups() if g is not None)
        if m.group(1) is not None and ("<" in raw and ">" in raw):
            for chunk in TAGTEXT.findall(raw):
                chunk = normal(placeholders(chunk))
                if visible(re.sub(r"\{\d+\}", "", chunk)):
                    found.append(chunk)
            for value in ATTR_IN_TEMPLATE.findall(raw):
                value = normal(placeholders(value))
                if visible(re.sub(r"\{\d+\}", "", value)):
                    found.append(value)
            continue
        value = normal(placeholders(raw) if m.group(1) is not None else raw)
        if "<" in value or "\\n" in value and len(value) > 300:
            continue
        if visible(re.sub(r"\{\d+\}", "", value)):
            found.append(value)
    return found


def from_manifest(data: dict) -> list[str]:
    out = [str(data.get(k)) for k in ("name", "title", "description") if data.get(k)]
    out += [str(c) for c in data.get("capabilities", []) if c]
    for setting in data.get("settings", []):
        if isinstance(setting, dict):
            out += [str(setting[k]) for k in ("label", "help", "placeholder") if setting.get(k)]
            out += [str(o.get("label")) for o in setting.get("options", []) if isinstance(o, dict) and o.get("label")]
    return [normal(s) for s in out if WORDY.search(s)]


HTTP_DETAIL = re.compile(r"HTTPException\(\s*\d+\s*,\s*f?\"([^\"]+)\"")


def from_python(text: str) -> list[str]:
    out = []
    for value in HTTP_DETAIL.findall(text):
        value = normal(re.sub(r"\{[^}]*\}", "{0}", value))
        if visible(re.sub(r"\{\d+\}", "", value)):
            out.append(value)
    return out


DICT_BLOCKS = {"backend/config.py": "EDITABLE_KEYS", "backend/feature_registry.py": "CATEGORIES", "backend/state.py": "PHASES"}
DICT_VALUE = re.compile(r"^\s*\"[A-Za-z0-9_]+\"\s*:\s*\"((?:[^\"\\]|\\.)+)\"", re.M)


def from_dict_block(text: str, name: str) -> list[str]:
    start = text.find(f"{name} = {{")
    if start < 0:
        return []
    end = text.find("\n}", start)
    return [normal(v.replace("\\\"", "\"")) for v in DICT_VALUE.findall(text[start:end]) if WORDY.search(v)]


def sources() -> list[Path]:
    globs = ("features/*/admin*.html", "features/*/admin*.js", "features/*/feature.json", "web/admin/*.html", "web/admin/*.js",
             "web/display/*.html", "web/display/*.js", "web/shared/*.js", "web/monitor/*.html", "web/monitor/*.js", "web/screen/*.html", "web/screen/*.js", "widgets/*/widget.js", "widgets/*/widget.json",
             "features/*/*.py", "backend/*.py")
    return sorted({p for g in globs for p in ROOT.glob(g) if "language" not in p.parts})


def extract() -> dict[str, list[str]]:
    catalog: dict[str, list[str]] = {}
    for path in sources():
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".html":
            strings = from_html(text)
        elif path.suffix == ".js":
            strings = from_js(text)
        elif path.suffix == ".py":
            rel_path = str(path.relative_to(ROOT))
            strings = from_python(text) + (from_dict_block(text, DICT_BLOCKS[rel_path]) if rel_path in DICT_BLOCKS else [])
        else:
            try:
                data = json.loads(text)
            except ValueError:
                continue
            strings = from_manifest(data) if path.name == "feature.json" else [normal(str(data.get(k))) for k in ("name", "description") if data.get(k)]
        for s in strings:
            catalog.setdefault(s, [])
            rel = str(path.relative_to(ROOT))
            if rel not in catalog[s]:
                catalog[s].append(rel)
    return catalog


if __name__ == "__main__":
    found = extract()
    if "--count" in sys.argv:
        print(len(found))
    else:
        json.dump(found, sys.stdout, ensure_ascii=False, indent=1)
