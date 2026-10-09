import re

import httpx

from state import store


def vision_skill() -> tuple[str, dict]:
    from features.people.presence import describe
    pres = store.presence or {}
    if pres.get("status") not in ("ok",):
        return "La webcam non è disponibile in questo momento.", {"mode": "face"}
    people = pres.get("people", [])
    speech = describe(people)
    items = [{"label": p["name"], "value": ("vicino" if p["near"] else "lontano")
              + (f" · {p['confidence'] * 100:.0f}%" if p["known"] else ""),
              "status": "ok" if p["known"] else "warn"} for p in people]
    return speech, {"mode": "focus", "title": "Cosa vedo", "subtitle": "Riconoscimento facciale locale",
                    "panels": [{"type": "image", "title": "Webcam", "src": "/api/vision/snapshot.jpg"},
                               {"type": "list", "title": f"Persone ({len(people)})",
                                "items": items or [{"label": "Nessuno", "value": "", "status": ""}]}]}


_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
}


def _parse_italian_date(text: str) -> str | None:
    from datetime import date
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)(?:\s+(\d{4}))?\b", text, re.I)
    if m:
        d = int(m.group(1))
        mo = _MONTHS[m.group(2).lower()]
        y = int(m.group(3)) if m.group(3) else (date.today().year - 30)
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def _find_target_person(text: str) -> dict | None:
    from features.people import people
    profiles = people.all_profiles()
    if not profiles:
        return None

    # Check if a specific known person's name is mentioned
    text_lower = text.lower()
    for p in profiles:
        first = (p.get("first_name") or "").lower()
        full = (p.get("name") or "").lower()
        if (first and re.search(r"\b" + re.escape(first) + r"\b", text_lower)) or \
           (full and full in text_lower):
            return p

    # Check active webcam presence
    visible = [p for p in store.presence.get("people", []) if p.get("known")]
    if visible:
        top_slug = visible[0].get("slug")
        p = people.get(top_slug)
        if p:
            return p

    # Look for owner
    owner = next((p for p in profiles if p.get("role") == "owner"), None)
    if owner:
        return owner

    # Default to first profile or most recently seen
    return profiles[0]


async def person_info_skill(text: str) -> tuple[str, dict]:
    from datetime import date
    from features.people import people
    from features.people.api import sync_person_neuron

    p = _find_target_person(text)
    if not p:
        return ("Non ho ancora registrato nessuna persona nel sistema. "
                "Puoi presentarti dicendo «Mi chiamo...» o creare una scheda nella sezione Persone.",
                {"mode": "face"})

    slug = p["slug"]
    name = people.display_name(p)
    comp = people.computed(p)
    current_age = comp.get("age")

    # 1. WRITING / APPUNTANDO DETTAGLI IN AUTOMATICO
    # A) Impostare età: "ho 36 anni", "ricordati che ho 36 anni", "appunta che ho 36 anni"
    m_age = re.search(r"\b(?:ho|compio|appunta che ho|ricordati che ho)\s+(\d{1,3})\s+anni\b", text, re.I)
    if m_age:
        years = int(m_age.group(1))
        approx_year = date.today().year - years
        approx_birthday = f"{approx_year}-01-01"
        changes = {"birthday": approx_birthday}
        people.update(slug, changes)
        await sync_person_neuron(slug)
        try:
            from features.mind.mind import mind
            mind.memory.add(f"{name} ha {years} anni.", "conversazione", score=0.9, who=slug)
        except Exception:
            pass
        return (f"Ho appuntato nel tuo profilo che hai {years} anni, {name}.",
                {"mode": "focus", "title": f"Scheda: {name}", "subtitle": "Profilo aggiornato", "personal": True,
                 "panels": [{"type": "kv", "title": "Dati", "data": {"Nome": name, "Età": f"{years} anni", "Data nascita indicativa": approx_birthday}}]})

    # B) Impostare compleanno / data di nascita: "il mio compleanno è...", "sono nato il..."
    if re.search(r"\b(?:compleanno|sono nat[oa]|data di nascita)\b", text, re.I) and not re.search(r"\b(?:quando|qual [èe]|sai quando)\b", text, re.I):
        parsed = _parse_italian_date(text)
        if parsed:
            people.update(slug, {"birthday": parsed})
            await sync_person_neuron(slug)
            p = people.get(slug)
            new_age = people.computed(p).get("age")
            try:
                from features.mind.mind import mind
                mind.memory.add(f"La data di nascita di {name} è {parsed}.", "conversazione", score=0.95, who=slug)
            except Exception:
                pass
            age_str = f" (hai {new_age} anni)" if new_age is not None else ""
            return (f"Ho registrato la tua data di nascita ({parsed}){age_str} nel profilo, {name}.",
                    {"mode": "focus", "title": f"Scheda: {name}", "subtitle": "Compleanno salvato", "personal": True,
                     "panels": [{"type": "kv", "title": "Dati", "data": {"Nome": name, "Data di nascita": parsed, "Età": f"{new_age} anni" if new_age else "—"}}]})

    # C) Impostare lavoro: "il mio lavoro è...", "faccio il programmatore", "lavoro come..."
    m_job = re.search(r"\b(?:il mio lavoro [èe]|lavoro come|faccio (?:il|la|l')?)\s+([A-Za-zÀ-ÿ' ]{3,35})\b", text, re.I)
    if m_job and not re.search(r"\b(?:che lavoro|qual [èe])\b", text, re.I):
        job = m_job.group(1).strip()
        people.update(slug, {"occupation": job})
        await sync_person_neuron(slug)
        try:
            from features.mind.mind import mind
            mind.memory.add(f"{name} lavora come {job}.", "conversazione", score=0.9, who=slug)
        except Exception:
            pass
        return (f"Ho appuntato nel profilo che lavori come {job}, {name}.",
                {"mode": "focus", "title": f"Scheda: {name}", "subtitle": "Lavoro registrato", "personal": True,
                 "panels": [{"type": "kv", "title": "Dati", "data": {"Nome": name, "Lavoro": job}}]})

    # D) Impostare allergie: "sono allergico a...", "appunta che sono allergico a..."
    m_all = re.search(r"\b(?:sono allergico|sono allergica|allergia)\s+(?:a|ai|alle|agli|al)?\s*([A-Za-zÀ-ÿ' ]{2,30})\b", text, re.I)
    if m_all:
        item = m_all.group(1).strip()
        allergies = list(p.get("allergies") or [])
        if item not in allergies:
            allergies.append(item)
        people.update(slug, {"allergies": allergies, "share_health": True})
        await sync_person_neuron(slug)
        return (f"Ho annotato nel tuo profilo che hai un'allergia a: {item}.",
                {"mode": "focus", "title": f"Scheda: {name}", "subtitle": "Salute e Allergie", "personal": True,
                 "panels": [{"type": "kv", "title": "Allergie", "data": {"Allergie": ", ".join(allergies)}}]})

    # E) Appunti generali: "appunta che...", "ricordati che..."
    m_note = re.search(r"\b(?:appunta|ricordati|segna)\s+(?:che|nel profilo che)\s+(.+)", text, re.I)
    if m_note:
        note_text = m_note.group(1).strip(" .!?")
        notes = (p.get("notes") or "").strip()
        updated_notes = f"{notes}\n- {note_text}".strip()
        people.update(slug, {"notes": updated_notes})
        try:
            from features.mind.mind import mind
            mind.memory.add(f"Nota su {name}: {note_text}", "conversazione", score=0.85, who=slug)
        except Exception:
            pass
        return (f"Ho appuntato questo dettaglio nel tuo profilo, {name}: «{note_text}».",
                {"mode": "focus", "title": f"Scheda: {name}", "subtitle": "Dettaglio appuntato", "personal": True,
                 "panels": [{"type": "text", "title": "Appunto", "content": note_text}]})

    # 2. READING / LETTURA DETTAGLI
    # A) Chiedere età: "quanti anni ho?", "sai quanti anni ho?", "mi sai dire quanti anni ho?"
    if re.search(r"\b(?:quanti anni|che et[àa]|la mia et[àa])\b", text, re.I):
        if current_age is not None:
            bday_info = f" (sei nato il {p['birthday']})" if p.get("birthday") else ""
            speech = f"Hai {current_age} anni, {name}{bday_info}."
        else:
            speech = (f"Ti riconosco come {name}, ma non ho ancora appuntato la tua età o data di nascita. "
                      "Dimmi pure quanti anni hai o quando sei nato e lo memorizzo subito!")
        panels = [
            {"type": "image", "title": "Volto Frontale", "src": f"/api/vision/people/{slug}/photo.jpg"},
            {"type": "kv", "title": "Anagrafica", "data": {
                "Nome": name,
                "Età": f"{current_age} anni" if current_age is not None else "Non ancora specificata",
                "Compleanno": p.get("birthday") or "Non impostato",
                "Ruolo": p.get("role", "proprietario"),
            }}
        ]
        return speech, {"mode": "focus", "title": f"Scheda Persona: {name}", "subtitle": "Riconoscimento e Anagrafe", "personal": True, "panels": panels}

    # B) Chiedere compleanno
    if re.search(r"\b(?:quando sono nat|quando compio|compleanno|data di nascita)\b", text, re.I):
        if p.get("birthday"):
            speech = f"Il tuo compleanno è il {p['birthday']}, {name}."
            if current_age is not None:
                speech += f" Hai {current_age} anni."
        else:
            speech = f"Non ho ancora registrato la tua data di nascita nel profilo, {name}. Puoi dirmela quando vuoi!"
        return speech, {"mode": "focus", "title": f"Scheda: {name}", "subtitle": "Ricorrenze", "personal": True,
                        "panels": [{"type": "kv", "title": "Date", "data": {"Data di nascita": p.get("birthday") or "—", "Onomastico": comp.get("name_day") or "—"}}]}

    # C) Chiedere lavoro
    if re.search(r"\b(?:che lavoro|qual [èe] il mio lavoro)\b", text, re.I):
        if p.get("occupation"):
            speech = f"Lavori come {p['occupation']}, {name}."
        else:
            speech = f"Non hai ancora indicato il tuo lavoro nella scheda, {name}."
        return speech, {"mode": "focus", "title": f"Scheda: {name}", "subtitle": "Lavoro", "personal": True,
                        "panels": [{"type": "kv", "title": "Professione", "data": {"Lavoro": p.get("occupation") or "Non specificato"}}]}

    # D) "Cosa sai di me" / Profilo generale
    details = [f"ti chiami {name}"]
    if current_age is not None:
        details.append(f"hai {current_age} anni")
    if p.get("occupation"):
        details.append(f"lavori come {p['occupation']}")
    if p.get("allergies"):
        details.append(f"sei allergico a {', '.join(p['allergies'])}")
    if p.get("notes"):
        details.append(f"ho annotato: {p['notes'][:120]}")

    speech = f"Ecco cosa so di te, {name}: " + "; ".join(details) + "."
    return speech, {
        "mode": "focus",
        "title": f"Scheda Persona: {name}",
        "subtitle": "Anagrafe e Memoria Completa",
        "personal": True,
        "panels": [
            {"type": "image", "title": "Volto Frontale", "src": f"/api/vision/people/{slug}/photo.jpg"},
            {"type": "kv", "title": "Dati", "data": {
                "Nome": name,
                "Età": f"{current_age} anni" if current_age is not None else "Non registrata",
                "Data di nascita": p.get("birthday") or "Non registrata",
                "Lavoro": p.get("occupation") or "Non specificato",
                "Allergie": ", ".join(p.get("allergies") or []) or "Nessuna nota",
            }}
        ]
    }


_NAME_RE = re.compile(r"\b(?:mi chiamo|il mio nome [èe]|chiamami)\s+([A-Za-zÀ-ÿ'][A-Za-zÀ-ÿ' ]{1,38})", re.I)


async def introduce_skill(text: str) -> tuple[str, dict]:
    from features.people import people
    m = _NAME_RE.search(text)
    if not m:
        return "Non ho capito il nome, puoi ripeterlo?", {"mode": "face"}
    name = " ".join(w.capitalize() for w in m.group(1).split()[:3]).strip(" .,!?")
    visible = [p for p in store.presence.get("people", []) if p.get("known")]
    target = next((p for p in visible if p.get("auto")), None)
    if target is None:
        if visible:
            return (f"La riconosco già come {visible[0]['name']}. Se desidera cambiare nome, può farlo dal pannello "
                    "Persone.", {"mode": "face"})
        return ("Non vedo nessuno davanti alla webcam a cui associare il nome. "
                "Si metta di fronte a me per qualche secondo e riprovi.", {"mode": "face"})
    wanted = " ".join(name.lower().split())
    clash = next((p for p in people.all_profiles(light=True) if p["slug"] != target["slug"] and wanted in
                  {" ".join(people.display_name(p).lower().split()), str(p.get("first_name") or "").lower().strip()}), None)
    if clash:
        store.event("WARN", f"Possibile impersonificazione: il volto {target['slug']} si è presentato come {name}, "
                            f"nome già usato da {clash['slug']}", "people")
        return (f"Conosco già una persona chiamata {name}. Se sei tu, il proprietario può unire il tuo volto al tuo "
                "profilo dal pannello Persone.", {"mode": "face"})
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.patch(f"http://127.0.0.1:8091/people/{target['slug']}", json={"name": name})
        r.raise_for_status()
    people.ensure(target["slug"], name)
    people.update(target["slug"], {"name": name})
    store.event("INFO", f"{target['name']} si è presentato come {name}", "people")
    return (f"Piacere di conoscerla, {name}. Da ora la riconoscerò e imparerò le sue abitudini.",
            {"mode": "face"})


