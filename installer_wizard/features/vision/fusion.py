import logging
import sys
from pathlib import Path

import cv2
import numpy as np

import ircam

sys.path.append(str(Path(__file__).resolve().parents[1] / "biometrics"))
import embeddings as emb
import liveness as lv

log = logging.getLogger("atena.vision")
PAIR_MIN = 0.2
OFFSET_ALPHA = 0.05
OFFSET_LIMIT = 0.3
EVIDENCE_FRAMES = 3


class Fusion:

    def __init__(self, detector_path: Path, recognizer) -> None:
        self.detector = cv2.FaceDetectorYN.create(str(detector_path), "", (320, 240), 0.55, 0.3, 200)
        self.recognizer = recognizer
        self.gray: np.ndarray | None = None
        self.bgr: np.ndarray | None = None
        self.faces: list[dict] = []
        self.size = (0, 0)
        self.offset = [0.0, 0.0]

    def refresh(self, gray: np.ndarray | None) -> None:
        self.gray = gray
        if gray is None:
            self.faces, self.bgr = [], None
            return
        h, w = gray.shape[:2]
        self.size = (w, h)
        self.bgr = cv2.cvtColor(ircam.enhance(gray), cv2.COLOR_GRAY2BGR)
        self.detector.setInputSize((w, h))
        try:
            _, faces = self.detector.detect(self.bgr)
        except cv2.error as exc:
            log.warning("Riconoscimento del volto all'infrarosso non riuscito: %s", exc)
            faces = None
        self.faces = [] if faces is None else [{"box": tuple(int(v) for v in f[:4]), "face": f} for f in faces]

    @property
    def active(self) -> bool:
        return self.gray is not None

    def pair(self, rgb_box, rgb_size) -> dict | None:
        best, top = None, PAIR_MIN
        for f in self.faces:
            a = lv.box_agreement(rgb_box, rgb_size, f["box"], self.size, tuple(self.offset))
            if a > top:
                best, top = f, a
        if best is not None:
            best = {**best, "agreement": top}
        return best

    def feature(self, ir_face: dict | None) -> np.ndarray | None:
        if ir_face is None or self.bgr is None:
            return None
        try:
            return self.recognizer.feature(self.recognizer.alignCrop(self.bgr, ir_face["face"])).flatten()
        except cv2.error as exc:
            log.debug("Impronta del volto all'infrarosso non calcolata: %s", exc)
            return None

    def learn_offset(self, rgb_box, rgb_size, ir_face: dict) -> None:
        dx = (ir_face["box"][0] + ir_face["box"][2] / 2) / self.size[0] - (rgb_box[0] + rgb_box[2] / 2) / rgb_size[0]
        dy = (ir_face["box"][1] + ir_face["box"][3] / 2) / self.size[1] - (rgb_box[1] + rgb_box[3] / 2) / rgb_size[1]
        for i, value in enumerate((dx, dy)):
            self.offset[i] = float(np.clip(self.offset[i] + (value - self.offset[i]) * OFFSET_ALPHA, -OFFSET_LIMIT, OFFSET_LIMIT))

    def assess(self, track, ir_face: dict | None, rgb_size, person: dict | None, minimum: float) -> dict:
        if not self.active:
            return lv.assess(False, False, None, 0.0, None, minimum)
        found = ir_face is not None
        metrics = lv.metrics(self.gray, ir_face["box"]) if found else None
        support = None
        if found and track.ir_feature is not None and person is not None and person.get("ir") is not None:
            support = emb.score_against(person["ir"], track.ir_feature)
        result = lv.assess(True, found, metrics, ir_face["agreement"] if found else 0.0, support, minimum)
        if result["score"] is not None:
            track.live_score = lv.smooth(track.live_score, result["score"])
            result["state"] = "unknown" if track.frames < EVIDENCE_FRAMES else ("live" if track.live_score >= minimum else "spoof")
        return result
