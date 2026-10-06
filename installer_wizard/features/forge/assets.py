import json
import re
import shutil
from pathlib import Path

from feature_registry import USER_DIR as FEATURE_DIR
from feature_registry import registry as features

from features.desktop import desk as desk_module
from features.desktop.desk import desk

HERE = Path(__file__).parent
ID = re.compile(r"^[a-z][a-z0-9_-]{2,40}$")
SIZES = ("s", "m", "l")


def _own(folder: Path, base: Path) -> bool:
    try:
        folder.resolve().relative_to(base.resolve())
        return folder.resolve() != base.resolve()
    except ValueError:
        return False


def create_widget(spec: dict) -> dict:
    wid = str(spec.get("id", ""))
    if not ID.match(wid):
        raise ValueError("id non valido: minuscole, cifre, - e _ (da 3 a 41 caratteri)")
    desk.scan()
    current = desk.widgets.get(wid)
    if current and current["source"] != "ai":
        raise ValueError(f"«{wid}» è già un widget {'di sistema' if current['source'] == 'system' else 'dell’utente'}")
    manifest = {"id": wid, "name": str(spec.get("name") or wid)[:60], "icon": str(spec.get("icon") or "▣")[:4], "size": spec.get("size") if spec.get("size") in SIZES else "m",
                "priority": max(0, min(100, int(spec.get("priority", 40)))), "ttl": max(0, min(3600, int(spec.get("ttl", 300)))),
                "description": str(spec.get("description", ""))[:300], "personal": spec.get("personal") is True, "source": "ai",
                "demo": spec.get("demo") if isinstance(spec.get("demo"), dict) else {"title": str(spec.get("name") or wid), "text": "Esempio"}}
    folder = desk_module.USER_DIR / wid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "widget.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    (folder / "widget.js").write_text((HERE / "widget_template.js").read_text(encoding="utf-8").replace("__ID__", wid), encoding="utf-8")
    shutil.copyfile(HERE / "widget_template.css", folder / "widget.css")
    desk.scan()
    return manifest


def delete_widget(wid: str) -> bool:
    desk.scan()
    current = desk.widgets.get(wid)
    folder = desk_module.USER_DIR / wid
    if not current or current["source"] != "ai" or not _own(folder, desk_module.USER_DIR):
        return False
    desk.hide(wid)
    shutil.rmtree(folder)
    desk.scan()
    return True


def create_feature(spec: dict) -> dict:
    fid = str(spec.get("id", ""))
    if not ID.match(fid):
        raise ValueError("id non valido: minuscole, cifre, - e _ (da 3 a 41 caratteri)")
    features.scan()
    current = features.features.get(fid)
    if current and current["source"] != "ai":
        raise ValueError(f"«{fid}» è già una funzionalità esistente")
    manifest = {"id": fid, "name": str(spec.get("name") or fid)[:60], "icon": str(spec.get("icon") or "◆")[:4], "category": spec.get("category", "altro"),
                "description": str(spec.get("description", ""))[:400], "capabilities": [str(c)[:200] for c in (spec.get("capabilities") or [])[:12]],
                "settings": [], "source": "ai"}
    features._validate(dict(manifest), fid)
    folder = FEATURE_DIR / fid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "feature.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    features.scan()
    return manifest


def delete_feature(fid: str) -> bool:
    features.scan()
    current = features.features.get(fid)
    folder = FEATURE_DIR / fid
    if not current or current["source"] != "ai" or not _own(folder, FEATURE_DIR):
        return False
    shutil.rmtree(folder)
    features.scan()
    return True
