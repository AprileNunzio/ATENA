from datetime import datetime

DAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre"]


def when(iso: str, now: datetime) -> str:
    try:
        at = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(now.tzinfo)
    except ValueError:
        return ""
    days = (at.date() - now.date()).days
    day = "oggi" if days == 0 else "domani" if days == 1 else "ieri" if days == -1 else f"{DAYS[at.weekday()]} {at.day}"
    if abs(days) > 6:
        day += f" {MONTHS[at.month - 1]}"
    return f"{day} alle {at:%H:%M}"


def _score(m: dict) -> str:
    return f"{m['home']['short']} {m['home']['score'] or 0}, {m['away']['short']} {m['away']['score'] or 0}"


def match_speech(card: dict, team: dict, now: datetime) -> str:
    m = card["match"]
    other = m["away"] if m["home"]["id"] == team["id"] else m["home"]
    if card["kind"] == "live":
        return f"{team['short'] or team['name']} sta giocando contro {other['short']}: {_score(m)}, {m['clock'] or 'in corso'}."
    if card["kind"] in ("today", "next"):
        where = f", {m['venue']}" if m["venue"] else ""
        return f"Prossima partita: {m['home']['short']} contro {m['away']['short']}, {when(m['start'], now)} ({m['league_name']}{where})."
    mine, theirs = (m["home"], m["away"]) if m["home"]["id"] == team["id"] else (m["away"], m["home"])
    a, b = mine["score"] or 0, theirs["score"] or 0
    verdict = "ha vinto" if a > b else "ha perso" if a < b else "ha pareggiato"
    scorers = [f"{e['player']} {e['minute']}".strip() for e in m["events"] if e["kind"] == "goal" and e["side"] and m[e["side"]]["id"] == mine["id"]]
    tail = f" Gol di {', '.join(scorers[:4])}." if scorers else ""
    return f"{mine['short']} {verdict} {a} a {b} contro {other['short']} ({m['league_name']}, {when(m['start'], now)}).{tail}"


def table_speech(card: dict, team: dict | None) -> str:
    rows = card["rows"]
    if not rows:
        return f"La classifica di {card['league_name']} non è ancora disponibile."
    if team:
        row = next((r for r in rows if r["id"] == team["id"]), None)
        if row:
            return f"{row['short']} è {row['rank']}° in {card['league_name']} con {row['points']} punti in {row['played']} partite."
    top = ", ".join(f"{r['short']} {r['points']}" for r in rows[:3])
    return f"In testa alla {card['league_name']}: {top}."


def f1_speech(card: dict) -> str:
    mode = card.get("mode")
    if mode == "standings":
        d = card["drivers"][:3]
        return "Mondiale piloti: " + ", ".join(f"{x['name']} {x['points']:g}" for x in d) + "." if d else "Classifica non disponibile."
    race = card["race"]
    if mode == "live":
        return f"È in corso {card['session']['name'].lower()} del {race['name']}."
    if mode == "results":
        podium = ", ".join(f"{r['pos']}° {r['name']}" for r in card["results"][:3])
        return f"{race['name']}: {podium}."
    session = card["session"]
    now = datetime.now().astimezone()
    return f"Prossimo appuntamento: {session['name'].lower()} del {race['name']}, {when(session['start'], now)} ({race['place']})."
