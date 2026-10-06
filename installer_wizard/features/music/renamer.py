import logging
import shutil
import time
from pathlib import Path

from features.music import layout, naming, organizer
from features.music.db import db

log = logging.getLogger("atena.music")
COLUMNS = "id, path, title, artist, album_artist, album, track_no, disc_no, year"


def free(target: Path, taken: set) -> Path:
    n = 2
    candidate = target
    while candidate in taken or candidate.exists():
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    return candidate


def plan(limit: int | None = None) -> list[dict]:
    rows = db.rows(f"SELECT {COLUMNS} FROM tracks ORDER BY id")
    root = layout.root()
    taken = {root / r["path"] for r in rows}
    steps = []
    for row in rows:
        source = root / row["path"]
        relative = Path(row["path"]).relative_to(layout.LIBRARY) if row["path"].startswith(layout.LIBRARY + "/") else None
        if relative is None or not source.is_file():
            continue
        folder = naming.directory(row) if naming.needs_new_folder(relative, row) else source.parent
        if folder is None:
            continue
        target = folder / naming.filename(row, source.suffix)
        if target == source:
            continue
        if target in taken or target.exists():
            target = free(target, taken)
        taken.add(target)
        steps.append({"id": row["id"], "from": row["path"], "to": target.relative_to(root).as_posix()})
        if limit and len(steps) >= limit:
            break
    return steps


def move_one(step: dict) -> bool:
    root = layout.root()
    source, target = root / step["from"], root / step["to"]
    if not layout.inside(layout.library(), target) or target.exists() or not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    lyrics = source.with_suffix(".lrc")
    if lyrics.exists() and not target.with_suffix(".lrc").exists():
        shutil.move(str(lyrics), str(target.with_suffix(".lrc")))
    db.run("UPDATE tracks SET path=? WHERE id=?", (step["to"], step["id"]))
    return True


def run(limit: int = 60) -> dict:
    done, failed = 0, 0
    for step in plan(limit):
        try:
            if move_one(step):
                done += 1
                organizer.progress["moves"] = ([{"from": step["from"], "to": step["to"], "at": time.time()}] + organizer.progress["moves"])[:20]
            else:
                failed += 1
        except OSError as exc:
            failed += 1
            log.warning("Brano non rinominato (%s): %s", step["from"], exc)
    if done:
        organizer.prune_library()
    return {"renamed": done, "failed": failed}
