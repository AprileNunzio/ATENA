import json
import logging
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("atena.vision")
STATUS_FILE = Path(os.environ.get("ATENA_IR_STATUS", "/var/lib/atena/ir_status.json"))
DARK_MEAN = 6.0
FPS = 10
STATUS_EVERY = 5.0
STALE_AFTER = 3.0
FOURCC = {"GREY": "GREY", "Y8": "Y800", "Y16": "Y16 ", "Y10": "Y10 ", "Y12": "Y12 "}


def to_gray8(frame: np.ndarray | None) -> np.ndarray | None:
    if frame is None:
        return None
    gray = frame
    if gray.ndim == 3:
        if gray.shape[2] == 1 or np.array_equal(gray[:, :, 0], gray[:, :, 1]):
            gray = gray[:, :, 0]
        else:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    if gray.dtype == np.uint16:
        top = float(np.percentile(gray, 99.5))
        scale = 255.0 / max(top, 1.0)
        gray = np.clip(gray.astype(np.float32) * scale, 0, 255)
    return np.ascontiguousarray(gray.astype(np.uint8))


def enhance(gray: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)


def status_of(mean: float | None, frames: int, running: bool) -> str:
    if not running or not frames:
        return "no_frames"
    if mean is not None and mean < DARK_MEAN:
        return "dark"
    return "ok"


class IrCamera:

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.path: str | None = None
        self.mode: dict | None = None
        self.gray: np.ndarray | None = None
        self.stamp = 0.0
        self.frames = 0
        self.mean: float | None = None
        self.running = False
        self.written = 0.0
        self.last_state = ""
        threading.Thread(target=self._loop, daemon=True).start()

    def retarget(self, path: str | None, mode: dict | None) -> None:
        with self.lock:
            if path != self.path:
                self.gray, self.mean, self.frames = None, None, 0
            self.path, self.mode = path, mode

    def latest(self) -> np.ndarray | None:
        with self.lock:
            if self.gray is None or time.time() - self.stamp > STALE_AFTER:
                return None
            return self.gray

    def view(self) -> dict:
        with self.lock:
            return {"path": self.path, "state": status_of(self.mean, self.frames, self.running) if self.path else "absent",
                    "mean": None if self.mean is None else round(self.mean, 1), "at": time.time()}

    def _open(self, path: str, mode: dict | None):
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        if mode:
            name = FOURCC.get(str(mode.get("fourcc", "")).upper())
            if name:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*name))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, mode.get("width", 0) or 0)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, mode.get("height", 0) or 0)
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _publish(self, force: bool = False) -> None:
        view = self.view()
        if not force and view["state"] == self.last_state and time.time() - self.written < 60:
            return
        if not force and time.time() - self.written < STATUS_EVERY:
            return
        self.last_state, self.written = view["state"], time.time()
        try:
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATUS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(view), encoding="utf-8")
            os.replace(tmp, STATUS_FILE)
        except OSError as exc:
            log.debug("Stato dell'infrarosso non salvato: %s", exc)

    def _loop(self) -> None:
        while True:
            with self.lock:
                path, mode = self.path, self.mode
            if not path:
                self.running = False
                self._publish()
                time.sleep(2)
                continue
            cap = self._open(path, mode)
            if not cap.isOpened():
                self.running = False
                self._publish()
                time.sleep(8)
                continue
            self.running = True
            log.info("Sensore infrarosso aperto: %s", path)
            misses = 0
            while misses < 30:
                with self.lock:
                    if self.path != path:
                        break
                ok, frame = cap.read()
                gray = to_gray8(frame) if ok else None
                if gray is None:
                    misses += 1
                    time.sleep(0.2)
                    continue
                misses = 0
                with self.lock:
                    self.gray, self.stamp, self.mean = gray, time.time(), float(gray.mean())
                    self.frames += 1
                self._publish()
                time.sleep(1 / FPS)
            cap.release()
            self.running = False
            self._publish()
            time.sleep(3)
