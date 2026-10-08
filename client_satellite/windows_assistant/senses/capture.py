import ctypes
import ctypes.wintypes as wt
import io
import time

import cv2
import mss
from PIL import Image

from senses.windows import Window, user32

MAX_SIDE = 1600
WARMUP_FRAMES = 8


class CaptureError(RuntimeError):
    pass


def _jpeg(image: Image.Image) -> bytes:
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=82)
    return buffer.getvalue()


def _region(window: Window | None, screen: dict) -> dict:
    if not window:
        return screen
    rect = wt.RECT()
    if not user32.GetWindowRect(window.hwnd, ctypes.byref(rect)):
        return screen
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 50 or height <= 50:
        return screen
    return {"left": rect.left, "top": rect.top, "width": width, "height": height}


def window_image(window: Window | None) -> bytes:
    with mss.MSS() as shot:
        raw = shot.grab(_region(window, shot.monitors[1]))
        return _jpeg(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"))


def webcam_image(index: int = 0) -> bytes:
    camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    try:
        if not camera.isOpened():
            raise CaptureError("Webcam non trovata o già in uso da un altro programma")
        frame = None
        for _ in range(WARMUP_FRAMES):
            ok, image = camera.read()
            if ok:
                frame = image
            time.sleep(0.05)
        if frame is None:
            raise CaptureError("La webcam non ha restituito immagini")
        return _jpeg(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    finally:
        camera.release()
