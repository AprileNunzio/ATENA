import logging
import threading
import time

from connection.client import Client, ServerError
from connection.ear import EarStream
from permissions.catalog import Level
from permissions.policy import Policy
from voice.microphone import Microphone
from voice.speaker import Speaker

log = logging.getLogger("atena.voice")
FOLLOWUP_SECONDS = 8


class Voice:
    def __init__(self, client: Client, cfg: dict, policy: Policy, ui, on_security) -> None:
        self.client, self.cfg, self.policy, self.ui = client, cfg, policy, ui
        self.speaker = Speaker()
        self.ear = EarStream(client, self.on_event, self.on_link, on_security)
        self.mic = Microphone(self.ear.send_audio, cfg.get("mic_device"))
        self.speaking = False
        self.busy = lambda: False
        self.on_transcript = None

    def continuous(self) -> bool:
        return self.policy.level("senses.microphone") is not Level.DENY

    def start(self) -> None:
        self.ear.start()
        self.mic.start()
        self.mic.muted = not self.continuous()
        if self.mic.error:
            self.ui.dispatch.post(self.ui.note, "⚠ " + self.mic.error)
        threading.Thread(target=self._levels, daemon=True, name="levels").start()

    def stop(self) -> None:
        self.ear.stop()
        self.mic.stop()
        self.speaker.stop()

    def _levels(self) -> None:
        while True:
            self.ui.set_level(self.mic.level)
            time.sleep(0.05)

    def on_link(self, ok: bool, error: str) -> None:
        self.ui.dispatch.post(self.ui.set_state, "idle" if ok else "offline")

    def on_event(self, event: dict) -> None:
        kind, post = event.get("type"), self.ui.dispatch.post
        if kind == "wake":
            self.speaker.chime(True)
            post(self.ui.set_state, "listening")
            post(self.ui.show_panel)
        elif kind == "state":
            state = event.get("state")
            if state == "listening" and not self.busy():
                post(self.ui.set_state, "listening")
            elif state == "transcribing":
                post(self.ui.set_state, "thinking")
            elif state == "idle" and not self.busy() and not self.speaking:
                self.mic.muted = not self.continuous()
                post(self.ui.set_state, "idle")
        elif kind == "transcript" and (event.get("text") or "").strip():
            self.on_transcript(event["text"].strip(), event.get("lang"))
        elif kind == "barge":
            self.speaker.stop()
        elif kind == "wake_only":
            post(self.ui.set_state, "listening")
        elif kind == "mic_level" and event.get("advice") == "lower":
            post(self.ui.note, "🎙 Il microfono è un po' troppo alto: abbassalo nelle impostazioni audio di Windows.")

    def listen(self) -> None:
        if self.speaking:
            self.speaker.stop()
        if not self.ear.connected:
            self.ui.show_panel(focus=True)
            self.ui.note("🎙 Ascolto vocale non disponibile ora: scrivimi pure qui.")
            return
        self.mic.muted = False
        self.ear.send(type="listen")
        self.speaker.chime(True)
        self.ui.set_state("listening")
        self.ui.show_panel()

    def set_muted(self, muted: bool) -> None:
        self.mic.muted = muted
        self.ui.note("🔇 Microfono in pausa" if muted else "🎙 Microfono attivo")

    def answer(self, reply: str, lang: str | None, spoken: bool) -> None:
        if reply and self.cfg.get("voice"):
            self._speak(reply, lang)
        elif spoken:
            self.ear.send(type="followup", seconds=FOLLOWUP_SECONDS, conversation=True)

    def _speak(self, text: str, lang: str | None) -> None:
        try:
            wav = self.client.tts(text, lang)
        except ServerError as exc:
            log.info("Voce non disponibile: %s", exc)
            return
        self.speaking = True
        self.ui.dispatch.post(self.ui.set_state, "speaking")
        self.ear.send(type="speaking", on=True)
        was_muted = self.mic.muted
        if not self.cfg.get("headset"):
            self.mic.muted = True
        try:
            self.speaker.play_wav(wav)
        finally:
            self.mic.muted = was_muted
            self.speaking = False
            self.ear.send(type="speaking", on=False)
            self.ear.send(type="followup", seconds=FOLLOWUP_SECONDS, conversation=True)
            self.ui.dispatch.post(self.ui.set_state, "idle")
