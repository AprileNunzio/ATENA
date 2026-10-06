import logging
import os
import shutil
import time
from pathlib import Path

from features.music import hints, layout, naming, tags

log = logging.getLogger("atena.music")
SETTLE = 20
MANUAL_SETTLE = 3
DUPLICATES = "_duplicati"
RETRY = 600.0
HOLD = 3600.0
FIX_EVERY = 600.0
failed: dict[Path, float] = {}
held: dict[Path, float] = {}
clock = {"fixed": 0.0}
progress = {"moved": 0, "duplicates": 0, "failed": 0, "at": 0.0, "last": [], "errors": [], "moves": [], "unassigned": 0}


name = naming.clean
destination = naming.destination


def settled(path: Path, wait: float = SETTLE) -> bool:
    try:
        return time.time() - path.stat().st_mtime > wait
    except OSError:
        return False


def candidates() -> list[Path]:
    root = layout.root()
    found = [p for p in layout.inbox().rglob("*") if p.is_file() and layout.is_audio(p) and DUPLICATES not in p.parts]
    found += [p for p in root.iterdir() if p.is_file() and layout.is_audio(p)]
    now = time.time()
    return sorted(p for p in found if now - failed.get(p, 0.0) > RETRY and now - held.get(p, 0.0) > HOLD)


def everything() -> list[Path]:
    root = layout.root()
    found = [p for p in layout.inbox().rglob("*") if p.is_file() and layout.is_audio(p) and DUPLICATES not in p.parts]
    return sorted(found + [p for p in root.iterdir() if p.is_file() and layout.is_audio(p)])


def unassigned_files() -> list[dict]:
    out = []
    for path in everything():
        info = hints.overlay(path, tags.read(path))
        if naming.known_artist(info):
            continue
        out.append({"path": path.relative_to(layout.root()).as_posix(), "name": path.name, "title": info["title"], "artist": "", "album": "" if naming.no_album(info["album"]) else info["album"],
                    "year": info["year"] or "", "genre": info["genre"], "track_no": info["track_no"] or ""})
    return out


def pending() -> bool:
    return any(True for _ in candidates())


def unique(target: Path) -> Path:
    candidate, n = target, 2
    while candidate.exists():
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    return candidate


def move(source: Path) -> str:
    info = hints.overlay(source, tags.read(source))
    target = destination(info, source.suffix)
    if target is None:
        held[source] = time.time()
        return "unassigned"
    if not layout.inside(layout.library(), target):
        raise ValueError("percorso di destinazione non valido")
    if target.exists() and target.stat().st_size == source.stat().st_size:
        quarantine = layout.inbox() / DUPLICATES
        quarantine.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(unique(quarantine / source.name)))
        return "duplicates"
    target.parent.mkdir(parents=True, exist_ok=True)
    final = unique(target)
    shutil.move(str(source), str(final))
    lyrics = source.with_suffix(".lrc")
    if lyrics.exists():
        shutil.move(str(lyrics), str(final.with_suffix(".lrc")))
    hints.drop(source)
    progress["last"] = ([final.relative_to(layout.library()).as_posix()] + progress["last"])[:8]
    progress["moves"] = ([{"from": source.name, "to": final.relative_to(layout.root()).as_posix(), "at": time.time()}] + progress["moves"])[:20]
    return "moved"


def misplaced() -> list[Path]:
    base = layout.library()
    found = []
    for path in base.rglob("*"):
        if path.is_file() and layout.is_audio(path):
            inside = [p.lower() for p in path.relative_to(base).parts[:-1]]
            if any(p in tags.STRUCTURE for p in inside) or (inside and inside[0] in naming.UNASSIGNED):
                found.append(path)
    return found


def fix_misplaced() -> int:
    fixed = 0
    for path in misplaced():
        if not settled(path, MANUAL_SETTLE):
            continue
        try:
            shutil.move(str(path), str(unique(layout.inbox() / path.name)))
            fixed += 1
        except OSError as exc:
            log.warning("Brano in una cartella sbagliata non spostato (%s): %s", path.name, exc)
    return fixed


def prune_empty() -> None:
    inbox = layout.inbox()
    for folder, dirs, files in os.walk(inbox, topdown=False):
        path = Path(folder)
        if path != inbox and not files and not dirs and DUPLICATES not in path.parts:
            try:
                path.rmdir()
            except OSError:
                continue


def prune_library() -> None:
    base = layout.library()
    for folder, dirs, files in os.walk(base, topdown=False):
        path = Path(folder)
        if path != base and not files and not dirs:
            try:
                path.rmdir()
            except OSError:
                continue


def sweep(manual: bool = False) -> dict:
    progress["at"] = time.time()
    results = {"moved": 0, "duplicates": 0, "failed": 0, "waiting": 0, "unassigned": 0}
    if manual:
        failed.clear()
        held.clear()
        progress["errors"] = []
    if manual or time.time() - clock["fixed"] > FIX_EVERY:
        clock["fixed"] = time.time()
        results["fixed"] = fix_misplaced()
    for path in candidates():
        if not settled(path, MANUAL_SETTLE if manual else SETTLE):
            results["waiting"] += 1
            continue
        try:
            results[move(path)] += 1
        except (OSError, ValueError) as exc:
            results["failed"] += 1
            failed[path] = time.time()
            progress["errors"] = ([f"{path.name}: {exc}"] + progress["errors"])[:5]
            log.warning("Brano non smistato (%s): %s", path.name, exc)
    for key in ("moved", "duplicates", "failed"):
        progress[key] += results[key]
    progress["unassigned"] = len([p for p in held if p.exists()])
    prune_empty()
    prune_library()
    return results
