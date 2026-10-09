from datetime import datetime, timezone

from features.sports.catalog import LIVE, POST, PRE

KICKOFF_SOON_MIN = 15


def _start(match: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(match["start"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


def score_line(m: dict) -> str:
    h, a = m["home"], m["away"]
    return f"{h['short']} {h['score'] if h['score'] is not None else 0} - {a['score'] if a['score'] is not None else 0} {a['short']}"


def _goal_text(m: dict, side: str) -> str:
    scorer = next((e for e in reversed(m["events"]) if e["kind"] == "goal" and e["side"] == side), None)
    who = f" di {scorer['player']}" if scorer and scorer["player"] else ""
    minute = f" al {scorer['minute']}" if scorer and scorer["minute"] else ""
    return f"Gol {m[side]['short']}{who}{minute}! {score_line(m)}"


def diff(old: dict[str, dict], new: dict[str, dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    out = []
    for mid, m in new.items():
        before = old.get(mid)
        start = _start(m)
        if m["state"] == PRE and start and 0 <= (start - now).total_seconds() <= KICKOFF_SOON_MIN * 60:
            out.append({"kind": "soon", "match": m, "key": f"soon:{mid}",
                        "text": f"Tra poco {m['home']['short']} - {m['away']['short']} ({m['league_name']})"})
        if before is None:
            continue
        if before["state"] == PRE and m["state"] == LIVE:
            out.append({"kind": "kickoff", "match": m, "key": f"kickoff:{mid}",
                        "text": f"È iniziata {m['home']['short']} - {m['away']['short']}"})
        if m["state"] in (LIVE, POST):
            for side in ("home", "away"):
                was, now_score = before[side]["score"] or 0, m[side]["score"] or 0
                if now_score > was:
                    out.append({"kind": "goal", "match": m, "side": side, "key": f"goal:{mid}:{side}:{now_score}",
                                "text": _goal_text(m, side)})
            reds = sum(1 for e in m["events"] if e["kind"] == "red") - sum(1 for e in before["events"] if e["kind"] == "red")
            if reds > 0:
                out.append({"kind": "red", "match": m, "key": f"red:{mid}:{len(m['events'])}",
                            "text": f"Espulsione in {m['home']['short']} - {m['away']['short']}"})
        if before["state"] != POST and m["state"] == POST:
            out.append({"kind": "final", "match": m, "key": f"final:{mid}", "text": f"Finale: {score_line(m)}"})
    return out


def involves(match: dict, team_ids: set[str]) -> bool:
    return match["home"]["id"] in team_ids or match["away"]["id"] in team_ids
