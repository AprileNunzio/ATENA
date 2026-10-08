"""Microfono (verso ATENA) e altoparlante (voce di ATENA, segnali acustici)."""
import io
import logging
import threading
import wave

import numpy as np
import sounddevice as sd

log = logging.getLogger("atena.audio")
RATE = 16000
BLOCK = 1600  # 100 ms


class Microphone:
    def __init__(self, on_pcm, device=None) -> None:
        self.on_pcm, self.device = on_pcm, device
        self.stream = None
        self.muted = False
        self.level = 0.0
        self.error = ""

    def start(self) -> None:
        self.stop()
        try:
            self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                         device=self.device, callback=self._native)
            self.stream.start()
        except Exception as exc:
            # Alcuni driver non accettano 16 kHz: si registra alla frequenza del dispositivo e si ricampiona
            log.info("16 kHz non supportati (%s): ricampionamento", exc)
            try:
                rate = int(sd.query_devices(self.device, "input")["default_samplerate"])
                self._ratio = RATE / rate
                self.stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                             blocksize=int(rate / 10), device=self.device, callback=self._resample)
                self.stream.start()
            except Exception as exc2:
                self.stream, self.error = None, f"Microfono non disponibile: {exc2}"
                log.warning(self.error)
                return
        self.error = ""

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _emit(self, pcm16: np.ndarray) -> None:
        self.level = float(np.sqrt(np.mean((pcm16.astype(np.float32) / 32768.0) ** 2))) if len(pcm16) else 0.0
        if not self.muted:
            self.on_pcm(pcm16.tobytes())

    def _native(self, data, frames, t, status) -> None:
        self._emit(data[:, 0].copy())

    def _resample(self, data, frames, t, status) -> None:
        src = data[:, 0]
        n = max(1, int(round(len(src) * self._ratio)))
        out = np.interp(np.linspace(0, len(src) - 1, n), np.arange(len(src)), src)
        self._emit((np.clip(out, -1, 1) * 32767).astype("<i2"))


class Speaker:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.playing = threading.Event()
        self._stop = threading.Event()

    def play_wav(self, data: bytes) -> None:
        with wave.open(io.BytesIO(data)) as w:
            rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            frames = w.readframes(w.getnframes())
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
        audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
        audio = (audio - 128) / 128 if width == 1 else audio / float(np.iinfo(dtype).max)
        self.play(audio.reshape(-1, channels), rate)

    def play(self, audio: np.ndarray, rate: int) -> None:
        """Riproduce bloccando il thread chiamante; stop() la interrompe subito."""
        with self.lock:
            self._stop.clear()
            self.playing.set()
            try:
                sd.play(audio, rate)
                duration = len(audio) / rate
                waited = 0.0
                while waited < duration + 0.3 and not self._stop.is_set():
                    self._stop.wait(0.05)
                    waited += 0.05
                sd.stop()
            except Exception as exc:
                log.warning("Riproduzione non riuscita: %s", exc)
            finally:
                self.playing.clear()

    def stop(self) -> None:
        self._stop.set()

    def chime(self, rising: bool = True) -> None:
        """Due note morbide: salgono quando ATENA inizia ad ascoltare, scendono quando smette."""
        rate = 44100
        notes = (659.25, 987.77) if rising else (987.77, 659.25)
        parts = []
        for f in notes:
            t = np.arange(int(rate * 0.09)) / rate
            env = np.minimum(1, t * 80) * np.exp(-t * 18)
            parts.append(0.18 * env * np.sin(2 * np.pi * f * t))
        threading.Thread(target=self.play, args=(np.concatenate(parts).astype(np.float32), rate), daemon=True).start()
