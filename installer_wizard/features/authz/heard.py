import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass

KEEP_SECONDS = 45.0
SPACES = re.compile(r"[\W_]+", re.UNICODE)


@dataclass(frozen=True)
class VoiceProof:
    slug: str
    score: float
    text: str
    at: float
    device: str = "mic:local"


def normalize(text: str) -> str:
    return SPACES.sub(" ", str(text or "").lower()).strip()


class HeardLog:

    def __init__(self) -> None:
        self._items: deque[VoiceProof] = deque(maxlen=64)
        self._lock = threading.Lock()

    def record(self, slug: str, score: float, text: str, at: float | None = None, device: str = "mic:local") -> None:
        if not slug or not text:
            return
        moment = at or time.time()
        with self._lock:
            self._items.append(VoiceProof(slug, float(score), normalize(text), moment, device))
        from features.places.locate import locator
        locator.note(slug, "voice", device, min(1.0, max(0.3, float(score))), moment)

    def tap(self, message: str | bytes, device: str = "mic:local") -> None:
        if not isinstance(message, str) or '"transcript"' not in message:
            return
        try:
            event = json.loads(message)
        except ValueError:
            return
        if isinstance(event, dict) and event.get("type") == "transcript":
            self.record(str(event.get("speaker") or ""), float(event.get("speaker_score") or 0.0), str(event.get("text") or ""),
                        device=device)

    def verify(self, slug: str, text: str, now: float | None = None) -> VoiceProof | None:
        wanted = normalize(text)
        if not slug or not wanted:
            return None
        now = now or time.time()
        with self._lock:
            for proof in reversed(self._items):
                if now - proof.at > KEEP_SECONDS:
                    break
                if proof.slug == slug and proof.text == wanted:
                    return proof
        return None


heard = HeardLog()
