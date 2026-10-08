import asyncio
import logging
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
import learning
import selection
from fusion import Fusion
from gallery import FACES, Gallery, slugify
from ircam import IrCamera, enhance
from objects import ObjectDetector
from tracks import Track, facing, iou, reliable_unknown
from views import Views, router as views_router

log = logging.getLogger("atena.vision")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

MODELS = Path(os.environ.get("ATENA_VISION_MODELS", "/opt/atena-vision/models"))
DETECT_WIDTH = 640
PICK_CHECK = 5.0
PORT = int(os.environ.get("ATENA_VISION_PORT", "8091"))
OBJECT_MODEL = MODELS / "object_detection_nanodet_2022nov.onnx"
NEAR_RATIO = 0.16
DETECT_FPS = 4
OBJECT_EVERY = 1.2
FEATURE_EVERY = 3
ECHO_THRESHOLD = 0.20
UNKNOWN_MIN_RATIO = 0.05


class Vision:
    def __init__(self, gallery: Gallery) -> None:
        self.gallery = gallery
        self.status = "starting"
        self.error = ""
        self.raw = None
        self.annotated_jpeg = b""
        self.tracks: list[Track] = []
        self.size = (640, 480)
        self.lock = threading.Lock()
        self.enroll_request = None
        self.frame_id = 0
        self.last_process = 0.0
        self.fast_until = 0.0
        self.detector = cv2.FaceDetectorYN.create(str(MODELS / "face_detection_yunet_2023mar.onnx"), "",
                                                  self.size, 0.85, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(MODELS / "face_recognition_sface_2021dec.onnx"), "")
        self.fusion = Fusion(MODELS / "face_detection_yunet_2023mar.onnx", self.recognizer)
        self.ir = IrCamera()
        self.pick: dict = selection.current()
        self.det_size = self.size
        self.objects = ObjectDetector(OBJECT_MODEL) if OBJECT_MODEL.exists() else None
        threading.Thread(target=self._loop, daemon=True).start()
        if self.objects:
            threading.Thread(target=self._object_loop, daemon=True).start()

    def _open(self):
        self.pick = selection.current()
        width, height = selection.capture_size(self.pick["rgb_mode"], os.cpu_count() or 2)
        cap = cv2.VideoCapture(self.pick["rgb"], cv2.CAP_V4L2)
        if (self.pick["rgb_mode"] or {}).get("fourcc") == "MJPG":
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ir.retarget(self.pick["ir"] if selection.ir_enabled() else None, self.pick["ir_mode"])
        return cap

    def _repick(self, checked: float) -> bool:
        if time.time() - checked < PICK_CHECK:
            return False
        latest = selection.current()
        if latest["rgb"] != self.pick["rgb"]:
            return True
        self.ir.retarget(latest["ir"] if selection.ir_enabled() else None, latest["ir_mode"])
        self.pick = latest
        return False

    def _loop(self) -> None:
        while True:
            cap = self._open()
            if not cap.isOpened():
                self.status, self.error = "no_camera", f"Webcam non disponibile ({self.pick['rgb']})"
                time.sleep(10)
                continue
            self.status, self.error = "ok", ""
            log.info("Webcam aperta: %s (infrarossi: %s)", self.pick["rgb"], self.pick["ir"] or "no")
            failures, checked = 0, time.time()
            while failures < 30:
                start = time.time()
                if self._repick(checked):
                    log.info("Webcam cambiata: riapro il flusso")
                    break
                checked = start if start - checked >= PICK_CHECK else checked
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    time.sleep(0.2)
                    continue
                failures = 0
                with self.lock:
                    self.raw = frame.copy()
                    self.frame_id += 1
                if start - self.last_process >= 1 / DETECT_FPS:
                    self.last_process = start
                    try:
                        self._process(frame)
                    except cv2.error as exc:
                        log.warning("Errore di elaborazione: %s", exc)
                if start > self.fast_until:
                    time.sleep(max(0.0, 1 / DETECT_FPS - (time.time() - start)))
            cap.release()
            self.status, self.error = "no_camera", "Flusso video interrotto: riconnessione"
            time.sleep(3)

    def _object_loop(self) -> None:
        while True:
            time.sleep(OBJECT_EVERY)
            with self.lock:
                frame = None if self.raw is None else self.raw.copy()
            if frame is None:
                continue
            try:
                self.objects.update(frame, [t.box for t in self.tracks])
            except cv2.error as exc:
                log.warning("Riconoscimento oggetti non riuscito: %s", exc)
                time.sleep(10)

    def _process(self, frame) -> None:
        h, w = frame.shape[:2]
        self.size = (w, h)
        scale = min(1.0, DETECT_WIDTH / w)
        small = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1.0 else frame
        if (small.shape[1], small.shape[0]) != self.det_size:
            self.det_size = (small.shape[1], small.shape[0])
            self.detector.setInputSize(self.det_size)
        _, faces = self.detector.detect(small)
        faces = faces if faces is not None else []
        if scale < 1.0:
            faces = [np.concatenate([f[:14] / scale, f[14:]]) for f in faces]
        self.fusion.refresh(self.ir.latest() if selection.ir_enabled() else None)
        now = time.time()
        minimum = selection.liveness_minimum()

        unmatched = list(self.tracks)
        current, detections = [], []
        for face in faces:
            box = tuple(int(v) for v in face[:4])
            best = max(unmatched, key=lambda t: iou(t.box, box), default=None)
            track = best if best is not None and iou(best.box, box) > 0.25 else Track(box)
            if track in unmatched:
                unmatched.remove(track)
            track.box, track.last_seen = box, now
            track.facing = facing(face)
            track.frames += 1
            need = (len(track.votes) < 3 or track.frames % FEATURE_EVERY == 0
                    or self.enroll_request is not None)
            ir_face = self.fusion.pair(box, self.size) if self.fusion.active else None
            if need:
                feature = self.recognizer.feature(self.recognizer.alignCrop(frame, face)).flatten()
                track.feature = feature
                track.ir_feature = self.fusion.feature(ir_face) if ir_face else None
                verdict = self.gallery.match_ex(feature, track.ir_feature)
                track.votes.append((verdict["slug"], verdict["name"], verdict["score"]) if verdict["slug"]
                                   else (None, "Sconosciuto", verdict["score"]))
                track.ambiguous, track.possible = verdict["ambiguous"], verdict["names"]
                detections.append((box, feature, face, track.ir_feature))
            slug_now = track.identity()[0]
            person = self.gallery.people.get(slug_now) if slug_now else None
            if selection.liveness_mode() != "off":
                self.fusion.assess(track, ir_face, self.size, person, minimum)
                track.live_state = "unknown" if track.live_score is None or track.frames < 3 else (
                    "live" if track.live_score >= minimum else "spoof")
                if ir_face and slug_now and track.live_state == "live":
                    self.fusion.learn_offset(box, self.size, ir_face)
            current.append(track)
        self.tracks = current + [t for t in unmatched if now - t.last_seen < 1.5]
        self._mark_echoes()
        for box, feature, _, _ in detections:
            track = next((t for t in current if t.box == box), None)
            if track:
                self._learn(track, frame, feature)

        if self.enroll_request is not None and detections:
            largest = max(detections, key=lambda d: d[0][2] * d[0][3])
            req = self.enroll_request
            req["samples"].append(largest[1])
            if largest[3] is not None:
                req.setdefault("ir", []).append(largest[3])
            if req.get("photo") is None:
                req["photo"] = self._crop(frame, largest[0])

        self._annotate(frame)

    def _mark_echoes(self) -> None:
        known = {t.identity()[0] for t in self.tracks if t.identity()[0]}
        for t in self.tracks:
            t.echo_of = None
            if t.identity()[0] or t.feature is None or not known:
                continue
            slug, score = self.gallery.closest(t.feature)
            if slug in known and score >= ECHO_THRESHOLD:
                t.echo_of = slug

    def _crop(self, frame, box):
        x, y, bw, bh = box
        pad = int(bw * 0.35)
        return frame[max(0, y - pad):y + bh + pad, max(0, x - pad):x + bw + pad].copy()

    def _learn(self, track: Track, frame, feature) -> None:
        learning.learn(self, track, frame, feature)

    def _annotate(self, frame) -> None:
        for t in self.tracks:
            x, y, bw, bh = t.box
            slug, name, score = t.identity()
            color = (255, 224, 41) if slug else (120, 120, 120) if t.echo_of else (71, 181, 255)
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
            label = f"{name} {score:.2f}" if slug else "riflesso" if t.echo_of else name
            cv2.putText(frame, label, (x, max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        for o in (self.objects.objects if self.objects else []):
            if o["scenery"]:
                continue
            x, y, bw, bh = o["box"]
            color = (168, 255, 61) if o["held"] else (255, 120, 180)
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 1)
            cv2.putText(frame, o["label"], (x, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with self.lock:
                self.annotated_jpeg = jpg.tobytes()

    def _visible(self, t: Track, now: float) -> bool:
        if t.identity()[0]:
            return True
        return not t.echo_of and reliable_unknown(t, now) and t.box[2] / (self.size[0] or 640) >= UNKNOWN_MIN_RATIO

    def presence(self) -> dict:
        w = self.size[0] or 640
        now = time.time()
        people = []
        for t in self.tracks:
            if not self._visible(t, now):
                continue
            slug, name, score = t.identity()
            bx, by, bw, bh = t.box
            ratio = bw / w
            h = self.size[1] or 480
            person = self.gallery.people.get(slug, {}) if slug else {}
            spoof = selection.liveness_mode() == "strict" and t.live_state == "spoof"
            if spoof:
                slug, name = None, "Foto o schermo"
            people.append({"track": t.id, "slug": slug, "name": name, "known": slug is not None,
                           "liveness": {"state": t.live_state, "score": None if t.live_score is None else round(t.live_score, 3)},
                           "ambiguous": t.ambiguous, "possible": t.possible,
                           "auto": bool(person.get("auto")), "facing": t.facing,
                           "confidence": round(score, 3), "proximity": round(ratio, 3),
                           "near": ratio >= NEAR_RATIO, "since": t.first_seen,
                           "gaze": {"x": round((bx + bw / 2) / (w or 640), 3),
                                    "y": round((by + bh / 2) / h, 3)}})
        people.sort(key=lambda p: -p["proximity"])
        return {"status": self.status, "error": self.error, "people": people, "objects": self.visible_objects(),
                "frame": [int(self.size[0] or 0), int(self.size[1] or 0)],
                "ir": self.ir.view(), "time": now}

    def visible_objects(self) -> list:
        if not self.objects or time.time() - self.objects.updated > 10:
            return []
        return [o for o in self.objects.objects if not o["scenery"]]

    def hands_jpeg(self, width: int = 320) -> tuple[int, bytes]:
        self.fast_until = time.time() + 3
        with self.lock:
            frame, fid = (None, 0) if self.raw is None else (self.raw.copy(), self.frame_id)
        if frame is None:
            return 0, b""
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return fid, jpg.tobytes() if ok else b""

    def live_jpeg(self, quality: int = 80) -> tuple[int, bytes]:
        self.fast_until = time.time() + 3
        with self.lock:
            frame, fid = (None, 0) if self.raw is None else (self.raw.copy(), self.frame_id)
        if frame is None:
            return 0, b""
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return fid, jpg.tobytes() if ok else b""

    def raw_jpeg(self, quality: int = 88) -> bytes:
        with self.lock:
            frame = None if self.raw is None else self.raw.copy()
        if frame is None:
            return b""
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return jpg.tobytes() if ok else b""

    def ir_jpeg(self) -> bytes:
        gray = self.ir.latest()
        if gray is None:
            return b""
        ok, jpg = cv2.imencode(".jpg", enhance(gray), [cv2.IMWRITE_JPEG_QUALITY, 80])
        return jpg.tobytes() if ok else b""

    def enroll(self, name: str, seconds: float = 4.0) -> dict:
        self.enroll_request = {"samples": [], "photo": None}
        deadline = time.time() + seconds
        while time.time() < deadline:
            time.sleep(0.1)
        req, self.enroll_request = self.enroll_request, None
        if len(req["samples"]) < 5 or req["photo"] is None:
            raise ValueError("Volto non rilevato con sufficiente chiarezza: avvicinati e guarda la webcam")
        return self.gallery.save(name, req["samples"], req["photo"], ir=req.get("ir") or None)


gallery = Gallery()
vision = Vision(gallery)
app = FastAPI(title="Atena Vision", docs_url=None, redoc_url=None, openapi_url=None)
views = Views(vision, gallery, MODELS)
app.include_router(views_router(views))


@app.get("/health")
async def health():
    return {"status": vision.status, "error": vision.error, "people_enrolled": len(gallery.people),
            "objects": vision.objects is not None, "camera": vision.pick["rgb"], "ir": vision.ir.view(),
            "liveness": selection.liveness_mode(), "similar_pairs": len(gallery.twins)}


@app.get("/presence")
async def presence():
    return JSONResponse(vision.presence())


@app.get("/objects")
async def objects():
    return {"objects": vision.visible_objects()}


@app.get("/snapshot.jpg")
async def snapshot():
    with vision.lock:
        data = vision.annotated_jpeg
    if not data:
        raise HTTPException(503, "Nessun fotogramma")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/frame.jpg")
async def frame():
    data = vision.raw_jpeg()
    if not data:
        raise HTTPException(503, "Nessun fotogramma")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/stream.mjpg")
async def stream(request: Request):
    async def frames():
        while not await request.is_disconnected():
            with vision.lock:
                data = vision.annotated_jpeg
            if data:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            await asyncio.sleep(1 / DETECT_FPS)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/live.mjpg")
async def live(request: Request):
    async def frames():
        last = -1
        while not await request.is_disconnected():
            fid, data = vision.live_jpeg()
            if data and fid != last:
                last = fid
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            await asyncio.sleep(1 / 20)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/hands.mjpg")
async def hands(request: Request):
    async def frames():
        last = -1
        while not await request.is_disconnected():
            fid, data = vision.hands_jpeg()
            if data and fid != last:
                last = fid
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            await asyncio.sleep(1 / 24)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/people/health")
async def people_health():
    return {"people": gallery.health(), "twin_similarity": float(os.environ.get("ATENA_FACE_TWIN_SIM", "0.55"))}


@app.get("/ir.jpg")
async def ir_frame():
    data = vision.ir_jpeg()
    if not data:
        raise HTTPException(503, "Sensore infrarosso non disponibile")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/people")
async def people():
    return {"people": gallery.listing()}


@app.get("/people/{slug}/photo.jpg")
async def photo(slug: str):
    path = FACES / slugify(slug) / "photo.jpg"
    if not path.exists():
        raise HTTPException(404, "Foto non trovata")
    return Response(path.read_bytes(), media_type="image/jpeg")


@app.post("/people")
async def enroll(request: Request):
    name = str((await request.json()).get("name", "")).strip()
    if not name or len(name) > 40:
        raise HTTPException(400, "Nome non valido")
    if vision.status != "ok":
        raise HTTPException(503, vision.error or "Webcam non disponibile")
    try:
        person = await asyncio.to_thread(vision.enroll, name)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    log.info("Registrato: %s (%d campioni)", person["name"], person["samples"])
    return person


@app.patch("/people/{slug}")
async def rename(slug: str, request: Request):
    name = str((await request.json()).get("name", "")).strip()
    if not name or len(name) > 40:
        raise HTTPException(400, "Nome non valido")
    person = gallery.rename(slugify(slug), name)
    if not person:
        raise HTTPException(404, "Persona non trovata")
    log.info("Rinominato %s → %s", slug, name)
    return person


@app.post("/people/{slug}/merge")
async def merge(slug: str, request: Request):
    body = await request.json()
    target, name = str(body.get("into", "")).strip(), str(body.get("name", "")).strip()
    if not target or not name or len(name) > 80:
        raise HTTPException(400, "Destinazione non valida")
    try:
        return await asyncio.to_thread(gallery.merge, slug, target, name)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/people/{slug}")
async def forget(slug: str):
    if not gallery.delete(slugify(slug)):
        raise HTTPException(404, "Persona non trovata")
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
