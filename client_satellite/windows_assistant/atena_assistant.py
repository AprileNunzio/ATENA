"""ATENA Assistente per Windows: voce, vista e mani di ATENA sul tuo PC."""
import base64
import ctypes
import getpass
import logging
import os
import re
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import customtkinter  # noqa: E402,F401  (imposta per primo la consapevolezza DPI per monitor)

LOG = config.DIR / "assistant.log"
config.DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                    encoding="utf-8")
log = logging.getLogger("atena")

SCREEN_HINT = re.compile(r"\b(scherm|finestr|document|questo test|questa (?:pagina|mail|email|tabella|slide|foto)|"
                         r"questo (?:codice|errore|file|disegno|progetto|foglio)|sto (?:scrivendo|leggendo|guardando|"
                         r"lavorando)|cosa vedi|leggi|riassum|correggi|migliora|riformula|tradu|screen|this (?:page|"
                         r"document|code|error)|what.*see)", re.I)
WEBCAM_HINT = re.compile(r"\b(guardami|mi vedi|webcam|telecamera|come (?:sto|sono vestit)|cosa ho in mano|"
                         r"cosa (?:ti )?mostro|look at me|can you see me|what am i holding)", re.I)
MAX_ROUNDS = 4


def _single_instance() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, "ATENA_Assistente_Windows")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


class Assistant:
    def __init__(self, cfg: dict) -> None:
        import audio
        import link
        import senses
        from actions import Executor
        from ui import UI

        self.cfg = cfg
        self.link = link.Link(cfg)
        self.busy = threading.Lock()
        self.speaking = False
        self.ui = UI(cfg, {
            "ask": self.ask, "listen": self.listen, "stop": self.stop_speaking, "quit": self.quit,
            "mute": self.set_muted, "is_muted": lambda: self.mic.muted, "save": lambda: config.save(cfg),
            "settings_changed": self.settings_changed, "unpair": self.unpair,
            "autostart": config.autostart_enabled, "set_autostart": config.set_autostart,
        })
        self.focus = senses.Focus()
        self.focus.start()
        self.apps = senses.installed_apps()
        self.folders = senses.folders()
        self.senses = senses
        self.executor = Executor(self.focus, self.apps, [*self.folders.values(), *(cfg.get("extra_folders") or [])],
                                 confirm=lambda m: self.ui.call(self.ui.confirm, m), notify=self.ui.note)
        self.speaker = audio.Speaker()
        self.ear = link.EarStream(self.link, self.on_ear, self.on_link)
        self.mic = audio.Microphone(self.ear.send_audio, cfg.get("mic_device"))
        self.heartbeat = link.Heartbeat(self.link, self.report, self.on_commands,
                                        lambda: self.ui.post(self.unpair, True))
        self.hotkeys = []

    # -- avvio --------------------------------------------------------------------------------------------------
    def start(self) -> None:
        self.ear.start()
        self.heartbeat.start()
        self.mic.start()
        self.mic.muted = not self.cfg.get("wake", True)
        if self.mic.error:
            self.ui.post(self.ui.note, "⚠ " + self.mic.error)
        self._bind_hotkeys()
        threading.Thread(target=self._level_loop, daemon=True).start()
        self.ui.run()

    def _bind_hotkeys(self) -> None:
        import keyboard
        for h in self.hotkeys:
            try:
                keyboard.remove_hotkey(h)
            except (KeyError, ValueError):
                pass
        self.hotkeys = []
        try:
            self.hotkeys.append(keyboard.add_hotkey(self.cfg["hotkey"], lambda: self.ui.post(self.listen)))
            self.hotkeys.append(keyboard.add_hotkey("esc", self._esc, suppress=False))
        except (ValueError, ImportError) as exc:
            self.ui.post(self.ui.note, f"⚠ Tasti rapidi non validi ({self.cfg['hotkey']}): {exc}")

    def _esc(self) -> None:
        if self.speaking:
            self.stop_speaking()

    def _level_loop(self) -> None:
        import time
        while True:
            self.ui.level = self.mic.level
            time.sleep(0.05)

    def report(self) -> dict:
        caps = ["voce", "microfono", "schermo", "azioni"] + (["webcam"] if self.cfg.get("webcam") else [])
        return {"version": config.VERSION, "hostname": socket.gethostname(), "capabilities": caps,
                "hardware": {"os": "windows"}}

    # -- eventi dal servizio di ascolto ---------------------------------------------------------------------------
    def on_link(self, ok: bool, error: str) -> None:
        self.ui.post(self.ui.set_state, "idle" if ok else "offline")

    def on_ear(self, ev: dict) -> None:
        kind = ev.get("type")
        if kind == "wake":
            self.speaker.chime(True)
            self.ui.post(self.ui.set_state, "listening")
            self.ui.post(self.ui.show_panel)
        elif kind == "state":
            state = ev.get("state")
            if state == "listening" and not self.busy.locked():
                self.ui.post(self.ui.set_state, "listening")
            elif state == "transcribing":
                self.ui.post(self.ui.set_state, "thinking")
            elif state == "idle" and not self.busy.locked() and not self.speaking:
                self.mic.muted = not self.cfg.get("wake", True)  # senza parola di attivazione si ascolta solo a richiesta
                self.ui.post(self.ui.set_state, "idle")
        elif kind == "transcript":
            text = (ev.get("text") or "").strip()
            if text:
                self.ask(text, ev.get("lang"), spoken=True)
        elif kind == "barge":
            self.stop_speaking()
        elif kind == "wake_only":
            self.ui.post(self.ui.set_state, "listening")

    def on_commands(self, commands: list) -> None:
        for cmd in commands:
            if cmd == "identify":
                threading.Thread(target=self.speak, args=("Sono qui, su questo computer.", None), daemon=True).start()
                self.ui.post(self.ui.show_panel)
            elif cmd == "restart":
                os.execv(sys.executable, [sys.executable, *sys.argv])

    # -- conversazione ------------------------------------------------------------------------------------------
    def listen(self) -> None:
        if self.speaking:
            self.stop_speaking()
        if not self.ear.connected:
            self.ui.show_panel(focus=True)
            self.ui.note("🎙 Ascolto vocale non disponibile ora: scrivimi pure qui.")
            return
        self.mic.muted = False
        self.ear.send(type="listen")
        self.speaker.chime(True)
        self.ui.set_state("listening")
        self.ui.show_panel()

    def ask(self, text: str, lang: str | None = None, spoken: bool = False) -> None:
        threading.Thread(target=self._ask, args=(text, lang, spoken), daemon=True).start()

    def _env(self) -> dict:
        names = sorted(self.apps)
        return {"user": getpass.getuser(), "host": socket.gethostname(), "folders": self.folders, "apps": names[:150]}

    def _capture(self, need: str, body: dict) -> str:
        w = self.focus.current()
        if need == "webcam":
            if not self.cfg.get("webcam"):
                return "La webcam è disattivata nelle impostazioni."
            self.ui.post(self.ui.note, "📷 Scatto una foto dalla webcam…")
            body["image"] = base64.b64encode(self.senses.webcam_image()).decode()
            body["image_source"] = "webcam"
            return ""
        content = self.senses.window_text(w) if w else ""
        if len(content) >= 120:
            body.setdefault("context", {})["content"] = content
            self.ui.post(self.ui.note, f"👁 Leggo «{w.title[:60]}»")
        else:
            body["image"] = base64.b64encode(self.senses.window_image(w)).decode()
            body["image_source"] = "screen"
            self.ui.post(self.ui.note, f"👁 Guardo {('«' + w.title[:60] + '»') if w else 'lo schermo'}")
        return ""

    def _ask(self, text: str, lang: str | None, spoken: bool) -> None:
        import link
        with self.busy:
            self.ui.post(self.ui.show_panel)
            self.ui.post(self.ui.say, "user", text)
            self.ui.post(self.ui.set_state, "thinking")
            w = self.focus.current()
            body = {"text": text, "lang": lang or "", "env": self._env(),
                    "context": {"window": w.title if w else "", "app": w.app if w else ""}}
            try:
                if WEBCAM_HINT.search(text):
                    problem = self._capture("webcam", body)
                    if problem:
                        self.ui.post(self.ui.note, "⚠ " + problem)
                elif SCREEN_HINT.search(text):
                    self._capture("screen", body)
                result = {}
                for _ in range(MAX_ROUNDS):
                    result = self.link.assist(body)
                    if result.get("ignored"):
                        self.ui.post(self.ui.set_state, "idle")
                        return
                    if result.get("need") and not body.get("image") and not body.get("context", {}).get("content"):
                        problem = self._capture(result["need"], body)
                        if problem:
                            result = {"reply": problem}
                            break
                        continue
                    actions = result.get("actions") or []
                    done, results = self.executor.run(actions) if actions else ([], [])
                    for line in done:
                        self.ui.post(self.ui.note, line)
                    if result.get("followup") and results:
                        body.pop("image", None)
                        body["results"] = results
                        continue
                    break
            except link.Unauthorized:
                self.ui.post(self.unpair, True)
                return
            except Exception as exc:
                log.exception("Richiesta non riuscita")
                self.ui.post(self.ui.say, "atena", f"Non ci sono riuscita: {exc}")
                self.ui.post(self.ui.set_state, "error")
                return
            reply, show = result.get("reply") or "", result.get("show") or ""
            if reply or show:
                self.ui.post(self.ui.say, "atena", reply, show)
            if reply and self.cfg.get("voice"):
                self.speak(reply, result.get("lang") or lang)
            elif spoken:
                self.ear.send(type="followup", seconds=8, conversation=True)
            self.ui.post(self.ui.set_state, "idle")

    def speak(self, text: str, lang: str | None) -> None:
        try:
            wav = self.link.tts(text, lang)
        except Exception as exc:
            log.info("Voce non disponibile: %s", exc)
            return
        self.speaking = True
        self.ui.post(self.ui.set_state, "speaking")
        self.ear.send(type="speaking", on=True)
        headset = self.cfg.get("headset")
        was_muted = self.mic.muted
        if not headset:
            self.mic.muted = True  # senza cuffie ATENA sentirebbe la propria voce
        try:
            self.speaker.play_wav(wav)
        finally:
            self.mic.muted = was_muted
            self.speaking = False
            self.ear.send(type="speaking", on=False)
            self.ear.send(type="followup", seconds=8, conversation=True)
            self.ui.post(self.ui.set_state, "idle")

    def stop_speaking(self) -> None:
        self.speaker.stop()

    def set_muted(self, muted: bool) -> None:
        self.mic.muted = muted
        self.ui.note("🔇 Microfono in pausa" if muted else "🎙 Microfono attivo")

    def settings_changed(self) -> None:
        config.save(self.cfg)
        self.mic.muted = not self.cfg.get("wake", True)
        self._bind_hotkeys()
        self.ui.note("✓ Impostazioni salvate")

    def unpair(self, revoked: bool = False) -> None:
        if not revoked and not self.ui.confirm("Scollegare questo PC da ATENA? Dovrai abbinarlo di nuovo con un codice."):
            return
        self.cfg["token"] = ""
        config.save(self.cfg)
        if revoked:
            from tkinter import messagebox
            messagebox.showwarning("ATENA", "Questo PC non è più autorizzato da ATENA. Riavvia l'assistente per abbinarlo di nuovo.")
        self.quit()

    def quit(self) -> None:
        self.ear.stop()
        self.heartbeat.stop()
        self.mic.stop()
        self.speaker.stop()
        self.ui.quit()
        os._exit(0)


def do_pair(cfg: dict, server: str, code: str, name: str, autostart: bool) -> None:
    import link
    server = config.normalize_server(server)
    if not server:
        raise ValueError("Scrivi l'indirizzo di ATENA")
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("Il codice deve avere 6 cifre")
    name = name or socket.gethostname()
    trial = {**cfg, "server": server, "name": name, "node_id": config.node_id_for(name)}
    token = link.Link(trial).pair(code, trial["node_id"], name)
    cfg.update(trial, token=token)
    config.save(cfg)
    try:
        config.set_autostart(autostart)
    except OSError:
        pass


def main() -> None:
    if not _single_instance():
        ctypes.windll.user32.MessageBoxW(None, "ATENA è già in esecuzione: cerca la sfera luminosa nell'angolo dello schermo.",
                                         "ATENA", 0x40)
        return
    cfg = config.load()
    if not cfg.get("token"):
        from ui import pairing_window
        if not pairing_window(cfg, lambda s, c, n, a: do_pair(cfg, s, c, n, a)):
            return
    try:
        Assistant(cfg).start()
    except Exception:
        log.exception("Avvio non riuscito")
        ctypes.windll.user32.MessageBoxW(None, f"ATENA non è riuscita ad avviarsi. Dettagli in:\n{LOG}", "ATENA", 0x10)


if __name__ == "__main__":
    main()
