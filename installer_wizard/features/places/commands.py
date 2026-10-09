import re

from features.authz.principal import acting
from features.places.locate import current_room
from features.places.store import store

WHERE_AM_I = re.compile(r"\b(dove (sono|mi trovo)|in (che|quale) stanza (sono|mi trovo)|where am i|which room am i|o[uù] suis[- ]je)\b", re.I)


async def answer(text: str) -> tuple[str, dict]:
    if not WHERE_AM_I.search(text or ""):
        raise LookupError("places")
    room = current_room.get()
    if room is None:
        return "Non so ancora in che stanza ti trovi: assegna una stanza ai miei microfoni e alle telecamere nel pannello Piani e stanze.", {"mode": "face"}
    floor = store.floors.get(room.floor_id)
    where = f"{room.name}" + (f", al {floor.name.lower()}" if floor else "")
    who = "" if acting().known else " (non ti ho ancora riconosciuto, mi baso sul dispositivo che stai usando)"
    return f"Sei qui: {where}{who}.", {"mode": "face"}
