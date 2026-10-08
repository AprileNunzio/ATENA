import base64
import getpass
import logging
import re
import socket
import threading

from actions.executor import Executor
from connection import tls
from connection.client import Client, ServerError, Unauthorized
from permissions.gate import Denied, Gate, Request
from permissions.policy import Policy
from senses import capture, reading
from senses.windows import Focus

log = logging.getLogger("atena.conversation")
MAX_ROUNDS = 4
TEXT_MIN = 120
SCREEN_HINT = re.compile(r"\b(scherm|finestr|document|questo test|questa (?:pagina|mail|email|tabella|slide|foto)|"
                         r"questo (?:codice|errore|file|disegno|progetto|foglio)|sto (?:scrivendo|leggendo|guardando|"
                         r"lavorando)|cosa vedi|leggi|riassum|correggi|migliora|riformula|tradu|screen|this (?:page|"
                         r"document|code|error)|what.*see|écran|cette page|ce document)", re.I)
WEBCAM_HINT = re.compile(r"\b(guardami|mi vedi|webcam|telecamera|come (?:sto|sono vestit)|cosa ho in mano|"
                         r"cosa (?:ti )?mostro|look at me|can you see me|what am i holding|regarde-moi)", re.I)


class Conversation:
    def __init__(self, client: Client, executor: Executor, gate: Gate, policy: Policy, focus: Focus, ui, voice,
                 environment) -> None:
        self.client, self.executor, self.gate, self.policy = client, executor, gate, policy
        self.focus, self.ui, self.voice, self.environment = focus, ui, voice, environment
        self.busy = threading.Lock()
        self.on_unauthorized = None
        self.on_security = None

    def ask(self, text: str, lang: str | None = None, spoken: bool = False) -> None:
        threading.Thread(target=self._ask, args=(text, lang, spoken), daemon=True, name="ask").start()

    def _post(self, fn, *args) -> None:
        self.ui.dispatch.post(fn, *args)

    def _body(self, text: str, lang: str | None) -> dict:
        window = self.focus.current()
        return {"text": text, "lang": lang or "",
                "env": {**self.environment(), "user": getpass.getuser(), "host": socket.gethostname(),
                        "permissions": self.policy.summary()},
                "context": {"window": window.title if window else "", "app": window.app if window else ""}}

    def _capture(self, need: str, body: dict) -> None:
        window = self.focus.current()
        if need == "webcam":
            self.gate.check(Request("senses.webcam", "Scattare una foto con la webcam"))
            self._post(self.ui.note, "📷 Scatto una foto dalla webcam…")
            body["image"], body["image_source"] = base64.b64encode(capture.webcam_image()).decode(), "webcam"
            return
        where = f"«{window.title[:60]}»" if window else "lo schermo"
        self.gate.check(Request("senses.screen", f"Guardare {where}"))
        content = reading.window_text(window) if window else ""
        if len(content) >= TEXT_MIN:
            body["context"]["content"] = content
            self._post(self.ui.note, f"👁 Leggo {where}")
        else:
            body["image"], body["image_source"] = base64.b64encode(capture.window_image(window)).decode(), "screen"
            self._post(self.ui.note, f"👁 Guardo {where}")

    def _rounds(self, body: dict) -> dict:
        result: dict = {}
        for _ in range(MAX_ROUNDS):
            result = self.client.assist(body)
            if result.get("ignored"):
                return result
            if result.get("need") and not body.get("image") and not body["context"].get("content"):
                self._capture(result["need"], body)
                continue
            lines, results = self.executor.run(result.get("actions") or [])
            for line in lines:
                self._post(self.ui.note, line)
            if result.get("followup") and results:
                body.pop("image", None)
                body["results"] = results
                continue
            return result
        return result

    def _ask(self, text: str, lang: str | None, spoken: bool) -> None:
        with self.busy:
            self._post(self.ui.show_panel)
            self._post(self.ui.say, "user", text)
            self._post(self.ui.set_state, "thinking")
            body = self._body(text, lang)
            try:
                if WEBCAM_HINT.search(text):
                    self._capture("webcam", body)
                elif SCREEN_HINT.search(text):
                    self._capture("screen", body)
                result = self._rounds(body)
            except Denied as exc:
                self._post(self.ui.say, "atena", f"Non posso: {exc}. Puoi cambiarlo in Permessi.")
                self._post(self.ui.set_state, "idle")
                return
            except Unauthorized:
                self.on_unauthorized()
                return
            except tls.PinMismatch as exc:
                self.on_security(str(exc))
                return
            except (ServerError, capture.CaptureError) as exc:
                log.warning("Richiesta non riuscita: %s", exc)
                self._post(self.ui.say, "atena", f"Non ci sono riuscita: {exc}")
                self._post(self.ui.set_state, "error")
                return
            if result.get("ignored"):
                self._post(self.ui.set_state, "idle")
                return
            reply, show = result.get("reply") or "", result.get("show") or ""
            if reply or show:
                self._post(self.ui.say, "atena", reply, show)
            self.voice.answer(reply, result.get("lang") or lang, spoken)
            self._post(self.ui.set_state, "idle")
