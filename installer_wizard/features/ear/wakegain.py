import numpy as np

from tuning import tuning

TARGET = 0.06
ATTACK_SMOOTH = 0.25
DECAY = 0.995


class WakeGain:

    def __init__(self) -> None:
        self.env = 0.0
        self.gain = 1.0

    def apply(self, frame: np.ndarray, rms: float, noise: float) -> np.ndarray:
        floor = max(noise * 2.2, 0.006)
        if rms > floor:
            self.env = max(rms, self.env * DECAY)
        else:
            self.env *= DECAY
        limit = tuning.wake_gain_limit()
        want = min(limit, max(1.0, TARGET / self.env)) if self.env > floor else 1.0
        self.gain += (want - self.gain) * ATTACK_SMOOTH
        if self.gain <= 1.02:
            return frame
        return np.clip(frame * self.gain, -1.0, 1.0)
