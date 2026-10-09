import logging
import os
import socket
import sys
import threading

import keyboard

from actions.executor import Executor
from app.conversation import Conversation
from app.errors import errors
from app.interface import Interface
from app import tvwindow
from app.voice import Voice
from backup.scheduler import BackupScheduler
from backup.snapshots import Snapshots
from connection import tls
from connection.client import Client, ServerError
from connection.heartbeat import Heartbeat
from connection.inbox import Inbox
from permissions.gate import Gate
from permissions.policy import Policy
from senses import places
from senses.windows import Focus
from settings import autostart, paths, store
from updates.updater import Updater

log = logging.getLogger("atena")


class Assistant:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.client = Client(cfg["server"], cfg["node_id"], cfg["token"], cfg["ca"])
        self.policy = Policy()
        self.ui = Interface(cfg, self._ui_actions())
        errors.attach(self.ui.root, lambda text: self.ui.dispatch.post(self.ui.note, text))
        self.gate = Gate(self.policy, lambda capability, request: self.ui.dispatch.call(self.ui.confirm, capability, request))
        self.focus = Focus()
        self.folders = places.folders()
        self.apps = places.installed_apps()
        self.snapshots = Snapshots()
        self.executor = self._executor()
        self.voice = Voice(self.client, cfg, self.policy, self.ui, self._security)
        self.conversation = Conversation(self.client, self.executor, self.gate, self.policy, self.focus, self.ui,
                                         self.voice, self._environment)
        self.conversation.on_unauthorized = lambda: self.ui.dispatch.post(self.unpair, True)
        self.conversation.on_security = self._security
        self.voice.busy = self.conversation.busy.locked
        self.voice.on_transcript = lambda text, lang: self.conversation.ask(text, lang, spoken=True)
        self.heartbeat = Heartbeat(self.client, self._report, self._on_reply,
                                   lambda: self.ui.dispatch.post(self.unpair, True), self._security)
        self.inbox = Inbox(self.client, lambda actions: self.ui.dispatch.post(self._actions, actions))
        self.backup = BackupScheduler(cfg, self.snapshots, lambda text: self.ui.dispatch.post(self.ui.note, text))
        self.updater = Updater(lambda text: self.ui.dispatch.post(self.ui.note, text), self.quit)
        self.hotkeys: list = []
        if self.policy.tampered:
            self.ui.alert("⚠ Il file dei permessi era stato modificato fuori da ATENA: ho ripristinato i valori sicuri.")

    def _executor(self) -> Executor:
        return Executor(self.gate, [*self.folders.values(), *self.policy.folders], self.focus, self.apps, self.snapshots)

    def _ui_actions(self) -> dict:
        return {
            "ask": lambda text: self.conversation.ask(text), "listen": lambda: self.voice.listen(),
            "stop": lambda: self.voice.speaker.stop(), "quit": self.quit, "is_muted": lambda: self.voice.mic.muted,
            "mute": lambda muted: self.voice.set_muted(muted), "save": lambda: store.save(self.cfg),
            "autostart": autostart.enabled, "fingerprint": lambda: tls.short(self.cfg["pin"]),
            "settings_saved": self._settings_saved, "unpair": self.unpair, "policy": lambda: self.policy,
            "permissions_changed": self._permissions_changed, "widgets": self.open_widgets,
        }

    def _environment(self) -> dict:
        return {"folders": self.folders, "apps": sorted(self.apps)[:150], "extra_folders": self.policy.folders}

    def _report(self) -> dict:
        return {"version": paths.VERSION, "hostname": socket.gethostname(), "hardware": {"os": "windows"},
                "capabilities": [k for k, v in self.policy.summary().items() if v != "deny"][:12]}

    def _on_reply(self, reply: dict) -> None:
        for command in reply.get("commands") or []:
            if command == "identify":
                self.ui.dispatch.post(self.ui.show_panel)
                self.voice.answer("Sono qui, su questo computer.", None, False)
            elif command == "restart":
                self.restart()
            elif command == "update":
                self.updater.check_now()
        if reply.get("actions"):
            self.ui.dispatch.post(self._actions, reply["actions"])

    def _actions(self, actions: list) -> None:
        for action in actions[:4]:
            if not isinstance(action, dict) or action.get("type") != "tv":
                continue
            url = str(action.get("url") or "")
            if not tvwindow.trusted(url, self.cfg["server"]):
                log.warning("Finestra TV rifiutata: indirizzo non di ATENA (%s)", url[:80])
                continue
            tvwindow.open_window(url)
            self.ui.note(f"📺 {str(action.get('title') or 'TV')[:60]}")

    def open_widgets(self) -> None:
        threading.Thread(target=self._open_widgets, daemon=True, name="widgets").start()

    def _open_widgets(self) -> None:
        try:
            link = self.client.request("/api/nodes/display-link", {})
            tvwindow.open_window(tvwindow.widgets_url(self.cfg["server"], str(link.get("path") or "")), tvwindow.WIDGETS)
        except (ServerError, ValueError) as exc:
            log.warning("Widget non aperti: %s", exc)
            self.ui.dispatch.post(self.ui.alert, f"Non riesco ad aprire i widget: {exc}")

    def _security(self, message: str) -> None:
        log.error(message)
        self.voice.stop()
        self.heartbeat.stop()
        self.ui.dispatch.post(self.ui.alert, f"🛑 {message}. Ricollega il PC solo se hai cambiato tu il certificato di ATENA.")

    def _bind_hotkeys(self) -> None:
        for handle in self.hotkeys:
            keyboard.remove_hotkey(handle)
        self.hotkeys = []
        try:
            self.hotkeys.append(keyboard.add_hotkey(self.cfg["hotkey"], lambda: self.ui.dispatch.post(self.voice.listen)))
        except ValueError as exc:
            self.ui.note(f"⚠ Tasti rapidi non validi ({self.cfg['hotkey']}): {exc}")
        self.hotkeys.append(keyboard.add_hotkey("esc", lambda: self.voice.speaking and self.voice.speaker.stop()))

    def _settings_saved(self, start_with_windows: bool) -> None:
        store.save(self.cfg)
        autostart.set_enabled(start_with_windows)
        self._bind_hotkeys()
        self.ui.note("✓ Impostazioni salvate")

    def _permissions_changed(self, key: str, level) -> None:
        if key == "folders":
            self.executor = self._executor()
            self.conversation.executor = self.executor
        if key == "senses.microphone":
            self.voice.mic.muted = not self.voice.continuous()

    def start(self) -> None:
        self.focus.start()
        self.voice.start()
        self.heartbeat.start()
        self.inbox.start()
        self.backup.start()
        self.updater.start()
        self._bind_hotkeys()
        self.ui.run()

    def unpair(self, revoked: bool = False) -> None:
        from tkinter import messagebox
        if not revoked and not messagebox.askyesno("ATENA", "Scollegare questo PC da ATENA? Dovrai abbinarlo di nuovo."):
            return
        self.cfg.update(token="", pin="", ca="")
        store.save(self.cfg)
        if revoked:
            messagebox.showwarning("ATENA", "Questo PC non è più autorizzato da ATENA. Riavvia l'assistente per abbinarlo di nuovo.")
        self.quit()

    def restart(self) -> None:
        self.voice.stop()
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def quit(self) -> None:
        self.voice.stop()
        self.heartbeat.stop()
        self.inbox.stop()
        self.backup.stop()
        self.updater.stop()
        self.ui.quit()
        os._exit(0)
