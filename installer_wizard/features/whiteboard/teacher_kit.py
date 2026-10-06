import base64
import re
import urllib.parse

import httpx

from features.presentation.infrastructure import wikimedia
from features.whiteboard import science
from features.whiteboard.board import CALLOUTS, CHARTS, board

TITLE_INK = "#ffd166"
RESULT_INK = "#7CFC9A"
PALETTE = ("#29e0ff", "#ffd166", "#ff4d6a", "#7cfc9a")
IMAGE_HOSTS = ("upload.wikimedia.org",)
MAX_IMAGE = 1_400_000
LANGS = re.compile(r"^[a-z]{2}$")
SUBJECTS = ("math", "physics", "chemistry", "science", "history", "geography", "language", "literature", "art", "music", "other")

LESSON_SYSTEM = (
    "You are a patient, brilliant school teacher using a digital whiteboard. Reply in {language}. Return ONLY JSON with this shape: "
    '{{"title": "short title", "summary": "one spoken sentence", "blocks": [ ... ]}} where each block is one of: '
    '{{"type": "text", "text": "one short sentence"}}, '
    '{{"type": "steps", "items": ["step 1", "step 2"]}}, '
    '{{"type": "callout", "kind": "info|tip|warning|definition|formula|example", "title": "...", "text": "..."}}, '
    '{{"type": "formula", "expression": "sympy-style math such as (x+1)^2 or sqrt(2)*x"}}, '
    '{{"type": "plot", "functions": ["x^2", "2*x+1"], "xmin": -5, "xmax": 5}}, '
    '{{"type": "chart", "kind": "bar|line|pie", "title": "...", "labels": ["a"], "values": [1]}}, '
    '{{"type": "table", "title": "...", "header": ["..."], "rows": [["..."]]}}, '
    '{{"type": "chemistry", "reaction": "H2 + O2 -> H2O"}}, '
    '{{"type": "image", "topic": "exact Wikipedia article title for a helpful picture"}}. '
    "Use at most {blocks} blocks, short lines under 80 characters, no markdown, no emoji. Prefer plots, tables, formulas and "
    "callouts whenever they make the idea clearer, like a real teacher would."
)
LANGUAGE_SYSTEM = (
    "You are a language teacher. Reply in {language}. For the word or sentence given, return ONLY JSON: "
    '{{"title": "...", "summary": "one spoken sentence", "table": {{"header": ["..."], "rows": [["..."]]}}, '
    '"notes": [{{"kind": "tip|warning|example|definition", "title": "...", "text": "..."}}]}}. '
    "Use the table for translations, conjugations or declensions; at most 10 rows and 3 notes, no markdown."
)
LANGUAGE_NAMES = {"it": "Italian", "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese"}


def heading(text: str) -> None:
    board.text(str(text)[:80], size=50, ink=TITLE_INK)


def plot_functions(functions: list[str], xmin: float = -10.0, xmax: float = 10.0, title: str = "") -> dict:
    series = [science.sample(f, xmin, xmax) for f in functions[:4]]
    ymin, ymax = min(s["ymin"] for s in series), max(s["ymax"] for s in series)
    return board.plot([{"label": s["label"], "color": PALETTE[i % len(PALETTE)], "points": s["points"]} for i, s in enumerate(series)],
                      xmin, xmax, ymin, ymax, title)


def formula(expression: str, label: str = "") -> dict:
    return board.formula(science.pretty(science.parse(expression)), label)


def calculus(kind: str, expression: str, point: str = "0") -> dict:
    data = science.calculus(kind, expression, point)
    board.formula(data["input"], data["title"])
    board.formula(data["result"], "=", ink=RESULT_INK)
    return data


def molar_mass(formula_text: str) -> dict:
    data = science.molar_mass(formula_text)
    board.table(["El.", "n", "g/mol"], [[p["element"], p["count"], p["mass"]] for p in data["parts"]], data["formula"])
    board.text(f"M({data['formula']}) = {data['total']} g/mol", size=42, ink=RESULT_INK)
    return data


def balance(reaction: str) -> dict:
    data = science.balance(reaction)
    board.text(science.chem(reaction), size=40)
    board.text(data["equation"], size=46, ink=RESULT_INK)
    return data


def physics(formula_text: str, known: dict, target: str) -> dict:
    data = science.physics(formula_text, known, target)
    board.text(data["formula"], size=42, ink=TITLE_INK)
    for name, value in data["known"].items():
        board.text(f"{name} = {value}", size=34)
    board.text(data["result"], size=46, ink=RESULT_INK)
    return data


def highlight_last(style: str = "highlight", count: int = 1) -> int:
    targets = [i for i in board.items if i.get("type") in ("text", "formula")][-max(1, min(10, count)):]
    for item in targets:
        board.mark(style, 0, 0, 0, 0, target=item["id"])
    return len(targets)


def credit(candidate: "wikimedia.Candidate") -> str:
    author = candidate.author or "autore sconosciuto"
    return f"{candidate.title[:40]} — {author[:36]}, {candidate.license} (Wikimedia Commons)"[:120]


async def commons_image(topic: str) -> tuple[str, str] | None:
    query = str(topic).strip()[:120]
    if not query:
        return None
    headers = {"User-Agent": "AtenaWhiteboard/1.0 (educational; https://github.com/AprileNunzio/ATENA)"}
    async with httpx.AsyncClient(timeout=8, follow_redirects=False, headers=headers) as client:
        try:
            r = await client.get(wikimedia.API, params=wikimedia.search_params(query))
            if r.status_code != 200:
                return None
            found = next((c for c in wikimedia.candidates(r.json()) if urllib.parse.urlparse(c.thumb).hostname in IMAGE_HOSTS), None)
            if found is None:
                return None
            img = await client.get(found.thumb)
        except (httpx.HTTPError, ValueError):
            return None
    kind = img.headers.get("content-type", "").split(";")[0]
    if img.status_code != 200 or kind not in ("image/png", "image/jpeg", "image/webp") or len(img.content) > MAX_IMAGE:
        return None
    return f"data:{kind};base64,{base64.b64encode(img.content).decode('ascii')}", credit(found)


async def image(topic: str, lang: str = "it") -> dict | None:
    found = await commons_image(topic)
    if not found:
        return None
    return board.image(found[0], found[1])


async def render_blocks(blocks: list, lang: str) -> int:
    drawn = 0
    for block in blocks[:12]:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        try:
            if kind == "text":
                board.paragraph(str(block.get("text", "")), size=38)
            elif kind == "steps":
                for n, step in enumerate([str(s) for s in block.get("items", [])][:8], 1):
                    board.paragraph(f"{n}. {step}", size=36)
            elif kind == "callout":
                board.callout(block.get("kind") if block.get("kind") in CALLOUTS else "info", str(block.get("title", "")),
                              str(block.get("text", "")))
            elif kind == "formula":
                formula(str(block.get("expression", "")))
            elif kind == "plot":
                plot_functions([str(f) for f in block.get("functions", [])], float(block.get("xmin", -10)), float(block.get("xmax", 10)))
            elif kind == "chart" and block.get("kind") in CHARTS:
                board.chart(block["kind"], list(block.get("labels", [])), list(block.get("values", [])), str(block.get("title", "")))
            elif kind == "table":
                board.table(list(block.get("header", [])), list(block.get("rows", [])), str(block.get("title", "")))
            elif kind == "chemistry":
                balance(str(block.get("reaction", "")))
            elif kind == "image":
                if await image(str(block.get("topic", "")), lang) is None:
                    continue
            else:
                continue
            drawn += 1
        except (ValueError, TypeError, science.ScienceError):
            continue
    return drawn


async def lesson(topic: str, lang: str = "it", subject: str = "other") -> dict:
    from features.brain.llm import generate
    language = LANGUAGE_NAMES.get(lang, "Italian")
    reply = await generate(f"Subject: {subject if subject in SUBJECTS else 'other'}. Teach this at the whiteboard: {topic[:300]}",
                           as_json=True, max_tokens=1600, temperature=0.3, kind="chat",
                           system=LESSON_SYSTEM.format(language=language, blocks=10), timeout=150)
    reply = reply if isinstance(reply, dict) else {}
    blocks = reply.get("blocks") if isinstance(reply.get("blocks"), list) else []
    if not blocks:
        raise ValueError("whiteboard.error.lesson")
    heading(str(reply.get("title") or topic))
    drawn = await render_blocks(blocks, lang)
    summary = str(reply.get("summary") or "")[:240]
    if summary:
        board.say(summary)
    return {"title": reply.get("title") or topic, "blocks": drawn, "speech": summary}


async def language_card(text: str, lang: str = "it") -> dict:
    from features.brain.llm import generate
    reply = await generate(f"Explain: {text[:200]}", as_json=True, max_tokens=900, temperature=0.2, kind="chat",
                           system=LANGUAGE_SYSTEM.format(language=LANGUAGE_NAMES.get(lang, "Italian")), timeout=120)
    reply = reply if isinstance(reply, dict) else {}
    table = reply.get("table") if isinstance(reply.get("table"), dict) else {}
    if not table.get("rows"):
        raise ValueError("whiteboard.error.lesson")
    heading(str(reply.get("title") or text))
    board.table(list(table.get("header") or []), list(table["rows"]))
    for note in (reply.get("notes") or [])[:3]:
        if isinstance(note, dict):
            board.callout(note.get("kind") if note.get("kind") in CALLOUTS else "tip", str(note.get("title", "")), str(note.get("text", "")))
    summary = str(reply.get("summary") or "")[:240]
    if summary:
        board.say(summary)
    return {"title": reply.get("title") or text, "speech": summary}
