import numpy as np

from tuning import tuning

TARGET = 0.06
LOUD = 0.25
QUIET = 0.012
CLIP = 0.985
CLIP_RATIO = 0.02
ATTACK_SMOOTH = 0.25
DECAY = 0.995
MIN_GAIN = 0.25
WINDOW = 160


class AutoLevel:

    def __init__(self) -> None:
        self.env = 0.0
        self.gain = 1.0
        self.speech = 0
        self.clipped = 0
        self.peak_rms = 0.0
        self.advice = ""
        self.pending = ""

    def apply(self, frame: np.ndarray, rms: float, noise: float) -> np.ndarray:
        floor = max(noise * 2.2, 0.006)
        if rms > floor:
            self.env = max(rms, self.env * DECAY)
            self._observe(frame, rms)
        else:
            self.env *= DECAY
        want = float(np.clip(TARGET / self.env, MIN_GAIN, tuning.wake_gain_limit())) if self.env > floor else 1.0
        self.gain += (want - self.gain) * ATTACK_SMOOTH
        if abs(self.gain - 1.0) <= 0.02:
            return frame
        return np.clip(frame * self.gain, -1.0, 1.0)

    def _observe(self, frame: np.ndarray, rms: float) -> None:
        self.speech += 1
        self.peak_rms = max(self.peak_rms, rms)
        if float(np.abs(frame).max()) >= CLIP:
            self.clipped += 1
        if self.speech >= WINDOW:
            self._judge()

    def _judge(self) -> None:
        clipping = self.clipped / max(1, self.speech)
        if clipping >= CLIP_RATIO or self.peak_rms >= LOUD:
            verdict = "lower"
        elif self.peak_rms < QUIET:
            verdict = "raise"
        else:
            verdict = "ok"
        if verdict != self.advice:
            self.advice = verdict
            self.pending = verdict
        self.speech, self.clipped, self.peak_rms = 0, 0, 0.0

    def take_advice(self) -> str:
        advice, self.pending = self.pending, ""
        return advice

    def status(self) -> dict:
        return {"gain": round(self.gain, 2), "advice": self.advice or "ok"}
