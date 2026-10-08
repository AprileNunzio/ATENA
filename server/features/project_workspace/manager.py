import os
import uuid
import time
import asyncio
from typing import Dict, Optional, List
from pydantic import BaseModel
from server.config.env import settings

class ProjectState(BaseModel):
    project_id: str
    name: str
    goal: str
    is_active: bool
    chat_history: List[Dict[str, str]]
    created_at: float
    updated_at: float

class ProjectWorkspaceManager:
    _instance = None

    def __new__(cls) -> "ProjectWorkspaceManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store_dir = os.path.join(settings.DATA_DIR, "projects")
            os.makedirs(cls._instance._store_dir, exist_ok=True)
            cls._instance._active = {}
        return cls._instance

    def _get_path(self, user_id: str) -> str:
        uid = user_id or "default"
        return os.path.join(self._store_dir, f"{uid}_active.json")

    def get_active(self, user_id: str) -> Optional[ProjectState]:
        uid = user_id or "default"
        if uid in self._active:
            return self._active[uid]
        path = self._get_path(uid)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    state = ProjectState.parse_raw(f.read())
                    if state.is_active:
                        self._active[uid] = state
                        self._notify_widget(state)
                        return state
            except Exception:
                pass
        return None

    def save(self, user_id: str, state: ProjectState) -> None:
        uid = user_id or "default"
        self._active[uid] = state
        state.updated_at = time.time()
        with open(self._get_path(uid), "w", encoding="utf-8") as f:
            f.write(state.json())

    def process_query(self, query: str, user_id: str) -> str:
        lower = query.lower()
        start_triggers = ["nuovo progetto", "crea un progetto", "lavoriamo a un progetto", "creami un sito web", "sviluppiamo", "creami un'app"]
        close_triggers = ["chiudi il progetto", "esci dal progetto", "termina il progetto"]

        state = self.get_active(user_id)

        if any(t in lower for t in close_triggers) and state:
            state.is_active = False
            self.save(user_id, state)
            self._notify_widget(None)
            return "Comando di sistema: il progetto attuale è stato chiuso con successo."

        if any(t in lower for t in start_triggers):
            name = "Nuovo Progetto"
            if "sito web" in lower: name = "Progetto Sito Web"
            state = ProjectState(
                project_id=uuid.uuid4().hex,
                name=name,
                goal=query,
                is_active=True,
                chat_history=[{"user": query}],
                created_at=time.time(),
                updated_at=time.time()
            )
            self.save(user_id, state)
            self._notify_widget(state)
            return f"[PROJECT_START: {name}] {query}"

        if state and state.is_active:
            state.chat_history.append({"user": query})
            self.save(user_id, state)
            self._notify_widget(state)
            return f"[CONTESTO PROGETTO ATTIVO: {state.goal}]\nRichiesta utente: {query}"

        return query

    def add_response(self, user_id: str, response: str) -> None:
        state = self.get_active(user_id)
        if state and state.is_active:
            state.chat_history.append({"agent": response})
            self.save(user_id, state)
            self._notify_widget(state)

    def _notify_widget(self, state: Optional[ProjectState]) -> None:
        try:
            from server.core.kernel.telemetry import NeuralTelemetry
            payload = state.dict() if state else {"is_active": False}
            asyncio.create_task(NeuralTelemetry.emit("project_mode", "system", payload))
        except Exception:
            pass

project_manager = ProjectWorkspaceManager()
