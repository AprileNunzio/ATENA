import re

ANY = [
    (re.compile(r"[*_#`>|]+"), " "),
    (re.compile(r"\bA\.T\.E\.N\.A\.?", re.I), "Atena"),
    (re.compile(r"\s*[—–]\s*"), ", "),
]
WORDS = {
    "it": ("il collegamento", "gradi", "per cento", "chilometri orari", "chilometri", r"\1 e \2"),
    "en": ("the link", "degrees", "percent", "kilometres per hour", "kilometres", r"\1 \2"),
    "fr": ("le lien", "degrés", "pour cent", "kilomètres heure", "kilomètres", r"\1 heures \2"),
    "es": ("el enlace", "grados", "por ciento", "kilómetros por hora", "kilómetros", r"\1 y \2"),
    "de": ("der Link", "Grad", "Prozent", "Kilometer pro Stunde", "Kilometer", r"\1 Uhr \2"),
    "pt": ("o link", "graus", "por cento", "quilômetros por hora", "quilômetros", r"\1 e \2"),
}
SPACES = re.compile(r"\s+")


def rules(lang: str) -> list:
    words = WORDS.get(lang)
    if words is None:
        return ANY + [(re.compile(r"https?://\S+"), " ")]
    link, degrees, percent, speed, distance, clock = words
    return ANY + [
        (re.compile(r"https?://\S+"), link),
        (re.compile(r"(\d)\s*°\s*C?"), rf"\1 {degrees}"),
        (re.compile(r"(\d)\s*%"), rf"\1 {percent}"),
        (re.compile(r"\bkm/h\b"), speed),
        (re.compile(r"\bkm\b"), distance),
        (re.compile(r"\bGB\b"), "gigabyte"),
        (re.compile(r"\bMB\b"), "megabyte"),
        (re.compile(r"\b(\d{1,2}):(\d{2})\b"), clock),
    ]


def normalize(text: str, lang: str) -> str:
    for pattern, repl in rules(lang):
        text = pattern.sub(repl, text)
    return SPACES.sub(" ", text).strip()
