import hashlib
import logging
import shutil
import time
from pathlib import Path

from settings import paths

log = logging.getLogger("atena.backup")
KEEP_DAYS = 30


class Snapshots:
    def __init__(self, root: Path = paths.BACKUP_DIR / "modifiche") -> None:
        self.root = root

    def save(self, source: Path) -> Path:
        stamp = time.strftime("%Y-%m-%d")
        digest = hashlib.sha256(str(source).lower().encode()).hexdigest()[:8]
        folder = self.root / stamp / f"{source.parent.name}-{digest}"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{time.strftime('%H%M%S')}_{source.name}"
        shutil.copy2(source, target)
        log.info("Copia di sicurezza di %s in %s", source, target)
        return target

    def prune(self) -> int:
        if not self.root.is_dir():
            return 0
        limit = time.time() - KEEP_DAYS * 86400
        removed = 0
        for day in self.root.iterdir():
            if day.is_dir() and day.stat().st_mtime < limit:
                shutil.rmtree(day)
                removed += 1
        if removed:
            log.info("Rimosse %d cartelle di copie più vecchie di %d giorni", removed, KEEP_DAYS)
        return removed
