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


def normalize(text: str) -> str:
    return SPACES.sub(" ", str(text or "").lower()).strip()


class HeardLog:

    def __init__(self) -> None:
        self._items: deque[VoiceProof] = deque(maxlen=64)
        self._lock = threading.Lock()

    def record(self, slug: str, score: float, text: str, at: float | None = None) -> None:
        if not slug or not text:
            return
        with self._lock:
            self._items.append(VoiceProof(slug, float(score), normalize(text), at or time.time()))

    def tap(self, message: str | bytes) -> None:
        if not isinstance(message, str) or '"transcript"' not in message:
            return
        try:
            event = json.loads(message)
        except ValueError:
            return
        if isinstance(event, dict) and event.get("type") == "transcript":
            self.record(str(event.get("speaker") or ""), float(event.get("speaker_score") or 0.0), str(event.get("text") or ""))

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
