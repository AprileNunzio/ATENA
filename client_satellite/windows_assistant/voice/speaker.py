import io
import logging
import threading
import wave

import numpy as np
import sounddevice as sd

log = logging.getLogger("atena.voice")
SAMPLE_TYPES = {1: np.uint8, 2: np.int16, 4: np.int32}


class Speaker:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.playing = threading.Event()
        self._stop = threading.Event()

    def play_wav(self, data: bytes) -> None:
        with wave.open(io.BytesIO(data)) as w:
            rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            frames = w.readframes(w.getnframes())
        dtype = SAMPLE_TYPES[width]
        audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
        audio = (audio - 128) / 128 if width == 1 else audio / float(np.iinfo(dtype).max)
        self.play(audio.reshape(-1, channels), rate)

    def play(self, audio: np.ndarray, rate: int) -> None:
        with self.lock:
            self._stop.clear()
            self.playing.set()
            try:
                sd.play(audio, rate)
                deadline = len(audio) / rate + 0.3
                waited = 0.0
                while waited < deadline and not self._stop.is_set():
                    self._stop.wait(0.05)
                    waited += 0.05
                sd.stop()
            except sd.PortAudioError as exc:
                log.warning("Riproduzione non riuscita: %s", exc)
            finally:
                self.playing.clear()

    def stop(self) -> None:
        self._stop.set()

    def chime(self, rising: bool = True) -> None:
        rate = 44100
        notes = (659.25, 987.77) if rising else (987.77, 659.25)
        parts = []
        for frequency in notes:
            t = np.arange(int(rate * 0.09)) / rate
            envelope = np.minimum(1, t * 80) * np.exp(-t * 18)
            parts.append(0.18 * envelope * np.sin(2 * np.pi * frequency * t))
        threading.Thread(target=self.play, args=(np.concatenate(parts).astype(np.float32), rate), daemon=True).start()
