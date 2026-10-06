import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path

import packages
from config import DEMO, STATE_DIR, read_env
from state import store
from steps import STEP_BY_ID, STEPS, Step, converge_step

log = logging.getLogger("atena.background")

QUEUE_FILE = STATE_DIR / "background.json"
DISK_PATHS = ("/", "/opt", "/var/lib")
DISK_MARGIN_GB = 2.0
RETRY_SECONDS = 600
MAX_ROUNDS = 6
CONVERSATION_QUIET_S = 45
RUNNING = ("checking", "running", "retrying")


def _free_gb() -> float:
    free = []
    for path in DISK_PATHS:
        if Path(path).exists():
            try:
                free.append(shutil.disk_usage(path).free / 2 ** 30)
            except OSError:
                continue
    return min(free) if free else 0.0


class BackgroundQueue:
    def __init__(self) -> None:
        self.paused = False
        self.order: list[str] = []
        self.current = ""
        self.finished = False
        self.last_activity = 0.0
        self.free_gb = _free_gb
        self.wake = asyncio.Event()
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.paused = bool(data.get("paused"))
        self.order = [i for i in data.get("order", []) if i in STEP_BY_ID and STEP_BY_ID[i].background]

    def _save(self) -> None:
        try:
            QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = QUEUE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"paused": self.paused, "order": self.order}), encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, QUEUE_FILE)
        except OSError as exc:
            log.warning("Coda in background non salvata: %s", exc)

    def steps(self) -> list[Step]:
        rank = {sid: i for i, sid in enumerate(self.order)}
        env = read_env()
        return sorted((s for s in STEPS if s.background and packages.step_wanted(s.id, env)), key=lambda s: (rank.get(s.id, len(rank)), s.priority))

    @staticmethod
    def status(step: Step) -> str:
        rec = store.steps.get(step.id, {})
        status = rec.get("status", "")
        if status == "done":
            return "done"
        if status in RUNNING:
            return "running"
        if status == "failed":
            return "failed"
        if status == "waiting_disk":
            return "waiting_disk"
        return "queued"

    def snapshot(self) -> dict:
        items, weight, done_weight = [], 0.0, 0.0
        for step in self.steps():
            rec = store.steps.get(step.id, {})
            status = self.status(step)
            progress = 100 if status == "done" else int(rec.get("progress", 0) or 0) if status == "running" else 0
            weight += step.size_gb
            done_weight += step.size_gb * progress / 100
            items.append({"id": step.id, "title": step.title, "description": step.description, "status": status,
                          "progress": progress, "message": str(rec.get("message", ""))[:160],
                          "detail": str(rec.get("detail", ""))[:160], "size_gb": step.size_gb})
        done = sum(1 for i in items if i["status"] == "done")
        return {"paused": self.paused, "conversation": self.in_conversation(), "current": self.current,
                "finished": self.finished or done == len(items), "done": done, "total": len(items),
                "progress": round(done_weight * 100 / weight, 1) if weight else 100.0, "items": items}

    def note_activity(self) -> None:
        self.last_activity = time.time()

    def in_conversation(self) -> bool:
        return time.time() - self.last_activity < CONVERSATION_QUIET_S

    def pause(self) -> None:
        self.paused = True
        self._save()
        store.event("INFO", "Installazioni in background in pausa", "background")
        store.touch()

    def resume(self) -> None:
        self.paused = False
        self._save()
        self.wake.set()
        store.event("INFO", "Installazioni in background riprese", "background")
        store.touch()

    def prioritize(self, step_id: str) -> bool:
        step = STEP_BY_ID.get(step_id)
        if not step or not step.background:
            return False
        self.order = [step_id] + [s.id for s in self.steps() if s.id != step_id]
        self._save()
        self.wake.set()
        store.event("INFO", f"«{step.title}» spostata in cima alla coda", "background")
        store.touch()
        return True

    async def _gate(self) -> None:
        while self.paused or self.in_conversation():
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    def _next(self, attempted: set) -> Step | None:
        for step in self.steps():
            if step.id not in attempted and self.status(step) != "done":
                return step
        return None

    def _disk_ok(self, step: Step) -> bool:
        if DEMO:
            return True
        need = step.size_gb + DISK_MARGIN_GB
        free = self.free_gb()
        rec = store.steps.setdefault(step.id, {})
        if free >= need:
            return True
        rec.update(status="waiting_disk", progress=0,
                   message=f"Servono {need:.1f} GB liberi, disponibili {free:.1f} GB")
        store.event("WARN", f"{step.title}: spazio su disco insufficiente ({free:.1f} GB liberi, servono {need:.1f} GB)",
                    "background")
        store.touch()
        return False

    async def run(self, lock: asyncio.Lock) -> None:
        self.finished = False
        for round_no in range(MAX_ROUNDS):
            attempted: set = set()
            while (step := self._next(attempted)) is not None:
                await self._gate()
                step = self._next(attempted)
                if step is None:
                    break
                attempted.add(step.id)
                if not self._disk_ok(step):
                    continue
                was_done = store.steps.get(step.id, {}).get("status") == "done"
                async with lock:
                    self.current = step.id
                    store.touch()
                    try:
                        ok = await converge_step(step, quiet=True)
                    except Exception as exc:
                        log.exception("Errore nell'installazione in background di %s", step.id)
                        store.steps.setdefault(step.id, {}).update(status="failed", message=str(exc)[:160])
                        ok = False
                    finally:
                        self.current = ""
                        store.touch()
                if not was_done:
                    store.event("INFO" if ok else "WARN",
                                f"{step.title}: {'pronta' if ok else 'non riuscita, riprovo più tardi'}", "background")
                await asyncio.sleep(1)
            if all(self.status(s) == "done" for s in self.steps()):
                break
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=RETRY_SECONDS * 2 ** round_no)
            except asyncio.TimeoutError:
                pass
        self.finished = True
        store.touch()


queue = BackgroundQueue()
