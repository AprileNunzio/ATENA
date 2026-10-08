import json
import logging
import os
import threading
import time
import zipfile
from pathlib import Path

from backup.snapshots import Snapshots
from settings import paths

log = logging.getLogger("atena.backup")
KEEP = 10
STATE_FILE = paths.DATA_DIR / "backup_state.json"
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "$recycle.bin"}
CHECK_SECONDS = 600


def archive(sources: list[str], target: Path, stamp: str) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    destination = target / f"ATENA-backup-{stamp}.zip"
    partial = destination.with_suffix(".partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for source in map(Path, sources):
            if not source.is_dir():
                log.warning("Cartella da salvare non trovata: %s", source)
                continue
            for folder, dirs, files in os.walk(source):
                dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
                for name in files:
                    file = Path(folder) / name
                    if target in file.parents:
                        continue
                    zf.write(file, Path(source.name) / file.relative_to(source))
    os.replace(partial, destination)
    return destination


def rotate(target: Path, keep: int = KEEP) -> list[Path]:
    copies = sorted(target.glob("ATENA-backup-*.zip"))
    removed = copies[:-keep] if len(copies) > keep else []
    for old in removed:
        old.unlink()
    return removed


class BackupScheduler(threading.Thread):
    def __init__(self, cfg: dict, snapshots: Snapshots, notify) -> None:
        super().__init__(daemon=True, name="backup")
        self.cfg, self.snapshots, self.notify = cfg, snapshots, notify
        self.stop_flag = threading.Event()

    def _state(self) -> dict:
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _save_state(self, state: dict) -> None:
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")

    def due(self, now: float) -> bool:
        sources, target = self.cfg.get("backup_folders") or [], self.cfg.get("backup_target") or ""
        if not sources or not target:
            return False
        return now - float(self._state().get("last", 0)) >= int(self.cfg.get("backup_hours") or 24) * 3600

    def run_once(self, now: float) -> Path:
        target = Path(self.cfg["backup_target"])
        made = archive(self.cfg["backup_folders"], target, time.strftime("%Y%m%d-%H%M%S", time.localtime(now)))
        rotate(target)
        self._save_state({**self._state(), "last": now, "file": str(made)})
        log.info("Backup completato: %s", made)
        return made

    def run(self) -> None:
        while not self.stop_flag.wait(CHECK_SECONDS):
            now = time.time()
            if now - float(self._state().get("pruned", 0)) > 86400:
                self.snapshots.prune()
                self._save_state({**self._state(), "pruned": now})
            if not self.due(now):
                continue
            try:
                made = self.run_once(now)
            except OSError as exc:
                log.error("Backup non riuscito: %s", exc)
                self.notify(f"⚠ Backup non riuscito: {exc}")
            else:
                self.notify(f"💾 Backup completato: {made.name}")

    def stop(self) -> None:
        self.stop_flag.set()
