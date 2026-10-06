import re

from fastapi import HTTPException

from features.cameras import live

SOURCE_RE = re.compile(r"^[wci]-[0-9a-f]{8}$")


def source_of(source_id: str) -> dict:
    found = live.find(source_id) if SOURCE_RE.match(source_id) else None
    if not found:
        raise HTTPException(404, "Telecamera non trovata")
    return found
