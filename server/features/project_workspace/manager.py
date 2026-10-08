import os
import uuid
import time
import asyncio
import glob
from typing import Dict, Optional, List
from pydantic import BaseModel
from server.config.env import settings

class ProjectState(BaseModel):
    project_id: str
    name: str
    goal: str
    status: str = "ACTIVE"
    visibility: str = "private"
    autonomous: bool = False
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
        return cls._instance

    def _user_dir(self, user_id: str) -> str:
        uid = user_id or "default"
        d = os.path.join(self._store_dir, uid)
        os.makedirs(d, exist_ok=True)
        return d

    def get_all(self, user_id: str) -> List[ProjectState]:
        projects = []
        for path in glob.glob(os.path.join(self._user_dir(user_id), "*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    projects.append(ProjectState.parse_raw(f.read()))
            except Exception: pass
        return sorted(projects, key=lambda x: x.updated_at, reverse=True)

    def get_active(self, user_id: str) -> Optional[ProjectState]:
        for p in self.get_all(user_id):
            if p.status == "ACTIVE": return p
        return None

    def save(self, user_id: str, state: ProjectState) -> None:
        state.updated_at = time.time()
        with open(os.path.join(self._user_dir(user_id), f"{state.project_id}.json"), "w", encoding="utf-8") as f:
            f.write(state.json())

    def process_query(self, query: str, user_id: str) -> str:
        lower = query.lower()
        
        list_triggers = ["quali progetti", "lista progetti", "progetti aperti", "list projects"]
        if any(t in lower for t in list_triggers):
            open_projs = [p for p in self.get_all(user_id) if p.status in ["ACTIVE", "PENDING"]]
            self._notify_list(open_projs)
            return "System command: showing projects list."

        close_triggers = ["chiudi il progetto", "esci dal progetto", "termina il progetto", "close project"]
        state = self.get_active(user_id)
        
        for t in close_triggers:
            if t in lower:
                target = lower.split(t)[-1].strip()
                if target:
                    for p in self.get_all(user_id):
                        if target in p.name.lower() and p.status != "CLOSED":
                            p.status = "CLOSED"
                            self.save(user_id, p)
                            if p.status == "ACTIVE": self._notify_widget(None)
                            return f"System command: project {p.name} closed."
                elif state:
                    state.status = "CLOSED"
                    self.save(user_id, state)
                    self._notify_widget(None)
                    return "System command: current project closed."

        start_triggers = ["nuovo progetto", "crea un progetto", "lavoriamo a un progetto", "creami un sito web", "sviluppiamo", "creami un'app", "new project"]
        if any(t in lower for t in start_triggers):
            if state:
                state.status = "PENDING"
                self.save(user_id, state)
            
            name = "Nuovo Progetto"
            if "sito web" in lower or "website" in lower: name = "Progetto Web"
            vis = "public" if "pubblico" in lower or "public" in lower else "private"
            auto = "autonomia" in lower or "notte" in lower or "background" in lower

            new_state = ProjectState(
                project_id=uuid.uuid4().hex,
                name=name,
                goal=query,
                status="ACTIVE",
                visibility=vis,
                autonomous=auto,
                chat_history=[{"user": query}],
                created_at=time.time(),
                updated_at=time.time()
            )
            self.save(user_id, new_state)
            self._notify_widget(new_state)
            return f"[PROJECT_START: {name} (Auto:{auto})] {query}"

        if state and state.status == "ACTIVE":
            if "autonomia" in lower or "notte" in lower:
                state.autonomous = True
            state.chat_history.append({"user": query})
            self.save(user_id, state)
            self._notify_widget(state)
            return f"[CONTESTO PROGETTO: {state.goal}] Richiesta: {query}"

        return query

    def add_response(self, user_id: str, response: str) -> None:
        state = self.get_active(user_id)
        if state and state.status == "ACTIVE":
            state.chat_history.append({"agent": response})
            self.save(user_id, state)
            self._notify_widget(state)

    def _notify_widget(self, state: Optional[ProjectState]) -> None:
        try:
            from server.core.kernel.telemetry import NeuralTelemetry
            payload = state.dict() if state else {"status": "CLOSED"}
            asyncio.create_task(NeuralTelemetry.emit("project_mode", "system", payload))
        except Exception: pass

    def _notify_list(self, projects: List[ProjectState]) -> None:
        try:
            from server.core.kernel.telemetry import NeuralTelemetry
            payload = {"is_list": True, "projects": [p.dict() for p in projects]}
            asyncio.create_task(NeuralTelemetry.emit("project_mode", "system", payload))
        except Exception: pass

project_manager = ProjectWorkspaceManager()
