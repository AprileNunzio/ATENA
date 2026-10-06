import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta

SYNONYMS = {
    "person": {"persona", "persone", "uomo", "donna", "bambino", "qualcuno", "gente", "person", "people", "man", "woman"},
    "car": {"auto", "automobile", "macchina", "macchine", "veicolo", "car", "vehicle"},
    "truck": {"camion", "furgone", "truck", "van"},
    "motorcycle": {"moto", "motorino", "scooter", "motorcycle"},
    "bicycle": {"bici", "bicicletta", "bicycle", "bike"},
    "dog": {"cane", "cani", "dog"},
    "cat": {"gatto", "gatti", "cat"},
    "bird": {"uccello", "uccelli", "bird"},
    "package": {"pacco", "pacchi", "consegna", "package", "parcel"},
    "license_plate": {"targa", "targhe", "plate"},
    "face": {"volto", "faccia", "viso", "face"},
    "motion": {"movimento", "mosso", "motion"},
}
ANIMALS = {"dog", "cat", "bird"}
STOP = set("""il lo la i gli le l un uno una di del dello della dei degli delle a al alla in nel nella su sul sulla con per tra fra
e ed o che mi trovami trova cerca mostrami mostra fammi vedere dove quando ci c chi cosa the a an of in on at find show me where when
was were is are di da dal dalla davanti dietro vicino""".split())
WORD = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class Query:
    since: float
    until: float
    labels: frozenset = field(default_factory=frozenset)
    terms: tuple = ()


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def parse(text: str, now: float | None = None) -> Query:
    now = now or time.time()
    words = WORD.findall(_plain(text))[:40]
    day = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    since, until = now - 7 * 86400, now
    labels: set[str] = set()
    terms: list[str] = []
    for i, w in enumerate(words):
        if w in ("oggi", "today"):
            since = day.timestamp()
        elif w in ("ieri", "yesterday"):
            since, until = (day - timedelta(days=1)).timestamp(), day.timestamp()
        elif w in ("stanotte", "tonight", "notte", "night"):
            since, until = (day - timedelta(hours=4)).timestamp(), (day + timedelta(hours=6)).timestamp()
        elif w in ("ora", "hour") and i and words[i - 1] in ("ultima", "last"):
            since = now - 3600
        elif w in ("settimana", "week"):
            since = now - 7 * 86400
        elif w in ("mese", "month"):
            since = now - 30 * 86400
        elif w in ("animale", "animali", "animal", "animals", "pet"):
            labels |= ANIMALS
        elif w in ("ultima", "last", "ultimo"):
            continue
        else:
            hit = next((label for label, words_ in SYNONYMS.items() if w in words_ or w == label), None)
            if hit:
                labels.add(hit)
            elif w not in STOP and len(w) >= 3:
                terms.append(w)
    return Query(since, until, frozenset(labels), tuple(terms[:6]))
