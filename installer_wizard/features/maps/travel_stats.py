import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("atena.maps")
KEEP = 60
MIN_GAP = 600.0


def bucket(dest: dict, when: datetime) -> str:
    label = re.sub(r"[^a-z0-9]+", "-", str(dest.get("label") or dest.get("name") or "x").lower()).strip("-")[:40] or "x"
    day = "wd" if when.weekday() < 5 else ("sat" if when.weekday() == 5 else "sun")
    return f"{label}|{day}|{when.hour}"


class TravelStats:

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, list] = {}
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("Statistiche dei tempi di viaggio non lette: %s", exc)

    def samples(self, dest: dict, when: datetime) -> list[float]:
        out: list[float] = []
        for shift in (-1, 0, 1):
            for row in self.data.get(bucket(dest, when + timedelta(hours=shift)), []):
                out.append(float(row[1]))
        return out

    def record(self, dest: dict, when: datetime, minutes: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        rows = self.data.setdefault(bucket(dest, when), [])
        if rows and now - float(rows[-1][0]) < MIN_GAP:
            return False
        rows.append([round(now), round(float(minutes), 1)])
        del rows[:-KEEP]
        self.save()
        return True

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Statistiche dei tempi di viaggio non salvate: %s", exc)
