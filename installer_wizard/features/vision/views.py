import asyncio
import json
import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request

from gallery import FACES, slugify

log = logging.getLogger("atena.vision")

KINDS = {
    "front": "Frontale", "three_left": "Tre quarti sinistra", "three_right": "Tre quarti destra",
    "left": "Profilo sinistro", "right": "Profilo destro", "up": "Testa alta", "down": "Testa bassa",
    "body": "Corpo intero", "body_back": "Corpo di spalle",
}
BODY = {"body", "body_back"}
MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1600
BODY_SIDE = 1280
OTHER_PERSON_MARGIN = 0.08
CAPTURE_SECONDS = 3.0


def decode(data: bytes) -> np.ndarray:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Immagine vuota o più grande di 8 MB")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None or img.ndim != 3:
        raise ValueError("File non riconosciuto come immagine")
    return shrink(img, MAX_SIDE)


def shrink(img: np.ndarray, side: int) -> np.ndarray:
    h, w = img.shape[:2]
    k = side / max(h, w)
    return cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA) if k < 1 else img


def pose_of(face: np.ndarray) -> str:
    rx, ry, lx, ly, nx, ny = face[4], face[5], face[6], face[7], face[8], face[9]
    span = max(1.0, abs(lx - rx))
    yaw = (nx - (rx + lx) / 2) / span
    eyes_y = (ry + ly) / 2
    pitch = (ny - eyes_y) / span
    if yaw > 0.55:
        return "left"
    if yaw < -0.55:
        return "right"
    if yaw > 0.22:
        return "three_left"
    if yaw < -0.22:
        return "three_right"
    if pitch < 0.45:
        return "up"
    if pitch > 1.0:
        return "down"
    return "front"


class Views:
    def __init__(self, vision, gallery, models: Path) -> None:
        self.vision, self.gallery = vision, gallery
        self.detector = cv2.FaceDetectorYN.create(str(models / "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.8, 0.3, 50)
        self.recognizer = cv2.FaceRecognizerSF.create(str(models / "face_recognition_sface_2021dec.onnx"), "")
        self.lock = threading.Lock()

    def _largest_face(self, img: np.ndarray):
        h, w = img.shape[:2]
        with self.lock:
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(img)
            if faces is None or not len(faces):
                return None, None
            face = max(faces, key=lambda f: f[2] * f[3])
            feature = self.recognizer.feature(self.recognizer.alignCrop(img, face)).flatten()
        return face, feature

    def _check_owner(self, slug: str, feature: np.ndarray) -> None:
        r = self.gallery.match_ex(feature)
        own = self.gallery.scores(feature)[0].get(slug, 0.0)
        if r["slug"] and r["slug"] != slug and r["score"] - own > OTHER_PERSON_MARGIN:
            raise ValueError(f"Il volto nella foto sembra di {r['name']}, non di questa persona")

    def _folder(self, slug: str, name: str, feature, photo) -> Path:
        d = FACES / slug
        if not (d / "meta.json").is_file():
            if feature is None:
                raise ValueError("Per una persona nuova serve prima una foto in cui si veda il viso")
            self.gallery.save(name or slug, [feature], photo, slug=slug)
        return d

    def _record(self, d: Path, kind: str, image: np.ndarray) -> str:
        photos = d / "photos"
        photos.mkdir(parents=True, exist_ok=True)
        fname = f"{kind}_{int(time.time() * 1000)}.jpg"
        cv2.imwrite(str(photos / fname), image, [cv2.IMWRITE_JPEG_QUALITY, 88])
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        views = meta.get("views") if isinstance(meta.get("views"), dict) else {}
        views[kind] = int(views.get(kind, 0)) + 1
        meta.update(views=views, updated=time.time())
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return fname

    def add(self, slug: str, name: str, kind: str, img: np.ndarray, samples: list | None = None, ir: list | None = None) -> dict:
        slug = slugify(slug)
        if kind not in KINDS and kind != "auto":
            raise ValueError("Tipo di vista sconosciuto")
        face, feature = self._largest_face(img)
        if kind == "auto":
            kind = pose_of(face) if face is not None else "body"
        if face is None and kind not in BODY and not samples:
            raise ValueError("Nessun volto trovato nella foto: avvicinati o usa una foto più nitida")
        feats = list(samples or []) + ([feature] if feature is not None else [])
        for f in feats[:3]:
            self._check_owner(slug, f)
        crop = img
        if face is not None and kind not in BODY:
            crop = self.vision._crop(img, tuple(int(v) for v in face[:4]))
        d = self._folder(slug, name, feats[0] if feats else None, crop)
        if feats:
            self.gallery.add_samples(slug, feats, ir)
        fname = self._record(d, kind, shrink(img, BODY_SIDE) if kind in BODY else crop)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        log.info("Vista %s aggiunta a %s (%d campioni)", kind, slug, meta.get("samples", 0))
        return {"slug": slug, "kind": kind, "label": KINDS[kind], "face": face is not None, "photo": fname,
                "samples": meta.get("samples", 0), "views": meta.get("views", {})}

    def capture(self, slug: str, name: str, kind: str) -> dict:
        if kind not in KINDS:
            raise ValueError("Tipo di vista sconosciuto")
        if self.vision.status != "ok":
            raise ValueError(self.vision.error or "Webcam non disponibile")
        if self.vision.enroll_request is not None:
            raise ValueError("Un'altra acquisizione è in corso")
        self.vision.enroll_request = {"samples": [], "photo": None}
        time.sleep(CAPTURE_SECONDS)
        req, self.vision.enroll_request = self.vision.enroll_request, None
        with self.vision.lock:
            frame = None if self.vision.raw is None else self.vision.raw.copy()
        if frame is None:
            raise ValueError("Nessun fotogramma dalla webcam")
        if kind not in BODY and len(req["samples"]) < 3:
            raise ValueError("Volto non visto abbastanza a lungo: resta fermo nella posizione indicata")
        return self.add(slug, name, kind, frame, req["samples"][-12:], (req.get("ir") or [])[-12:] or None)


def router(views: Views) -> APIRouter:
    r = APIRouter()

    def _params(request: Request) -> tuple[str, str]:
        kind = str(request.query_params.get("kind", "auto"))[:20]
        name = str(request.query_params.get("name", "")).strip()[:40]
        return kind, name

    @r.post("/people/{slug}/views")
    async def upload(slug: str, request: Request):
        kind, name = _params(request)
        data = await request.body()
        try:
            img = decode(data)
            return await asyncio.to_thread(views.add, slug, name, kind, img)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @r.post("/people/{slug}/views/capture")
    async def capture(slug: str, request: Request):
        kind, name = _params(request)
        try:
            return await asyncio.to_thread(views.capture, slug, name, kind)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @r.get("/views/kinds")
    async def kinds():
        return {"kinds": KINDS}

    return r
