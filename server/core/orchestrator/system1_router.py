import time
import math
import re
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class System1Intent(str, Enum):
    CONVERSATION = "conversation"
    ACTION_DIRECT = "action_direct"
    WHITEBOARD_CANVAS = "whiteboard_canvas"
    BROWSER_ACTION = "browser_action"
    COMPLEX_TASK = "complex_task"

class System1Decision(BaseModel):
    intent: System1Intent
    confidence: float
    latency_ms: float
    logits: Dict[str, float]
    target_agent: Optional[str] = None
    direct_action: Optional[str] = None
    surface_action: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

class System1Router:
    def __init__(self) -> None:
        self._action_tokens = {
            "accendi": ("home_assistant", "turn_on", 4.5),
            "spegni": ("home_assistant", "turn_off", 4.5),
            "luce": ("home_assistant", "toggle_light", 4.0),
            "luci": ("home_assistant", "toggle_light", 4.0),
            "termostato": ("home_assistant", "set_temp", 4.0),
            "temperatura": ("home_assistant", "get_temp", 3.8),
            "chiudi": ("home_assistant", "close_lock", 4.0),
            "apri": ("home_assistant", "open_lock", 2.8),
            "porta": ("home_assistant", "door_lock", 3.8),
            "volume": ("media_player", "set_volume", 4.2),
            "muta": ("media_player", "mute", 4.2),
            "play": ("media_player", "play", 4.5),
            "pausa": ("media_player", "pause", 4.5),
            "stop": ("media_player", "stop", 4.5),
            "suona": ("media_player", "play", 4.2),
            "canzone": ("media_player", "play_track", 3.8),
            "musica": ("media_player", "play_track", 3.8),
            "telecamera": ("vision_surveillance", "view_feed", 4.0),
            "telecamere": ("vision_surveillance", "view_feed", 4.0),
            "allarme": ("vision_surveillance", "alarm_status", 4.2),
            "intruso": ("vision_surveillance", "detect_intrusion", 4.0),
            "riavvia": ("sysops_automation", "restart_service", 4.2),
            "stato": ("sysops_automation", "system_status", 3.6),
            "ping": ("sysops_automation", "ping_host", 4.0),
        }
        self._chitchat_tokens = {
            "ciao": 6.0,
            "buongiorno": 6.0,
            "buonasera": 6.0,
            "salve": 5.5,
            "grazie": 5.5,
            "prego": 5.0,
            "come": 3.5,
            "stai": 5.0,
            "chi": 3.8,
            "sei": 4.5,
            "eccomi": 5.0,
            "hey": 5.5,
            "buondi": 5.5,
            "arrivederci": 5.5,
            "notte": 5.0,
            "buonanotte": 5.5,
            "ok": 4.0,
            "daccordo": 4.0,
            "perfetto": 4.0,
            "bene": 3.8,
        }
        self._whiteboard_tokens = {
            "lavagna": 6.5,
            "whiteboard": 6.5,
            "canvas": 6.0,
            "disegna": 5.0,
            "disegniamo": 5.5,
            "diagramma": 5.2,
            "schema": 5.0,
            "flusso": 4.8,
            "postit": 5.0,
            "schematizza": 5.2,
            "matematica": 6.0,
            "calcoli": 5.5,
            "calcolo": 5.5,
            "equazione": 5.5,
            "equazioni": 5.5,
            "algebra": 5.5,
        }
        self._browser_tokens = {
            "browser": 6.0,
            "sito": 5.2,
            "naviga": 5.5,
            "visita": 5.2,
            "google": 5.5,
            "amazon": 5.5,
            "youtube": 5.5,
            "github": 5.5,
            "wikipedia": 5.2,
            "url": 5.0,
            "link": 4.5,
            "web": 4.5,
        }
        self._complex_tokens = {
            "analizza": 5.0,
            "spiega": 4.5,
            "perché": 4.8,
            "perche": 4.8,
            "progetta": 5.5,
            "architettura": 5.2,
            "sviluppa": 5.0,
            "programma": 4.8,
            "scrivi": 3.8,
            "codice": 4.5,
            "refactoring": 5.2,
            "debug": 4.8,
            "ottimizza": 5.0,
            "confronta": 4.6,
            "ragiona": 5.5,
            "pensa": 5.2,
            "elabora": 4.8,
            "strategia": 5.2,
            "piano": 4.5,
            "sintesi": 4.8,
            "riassumi": 4.5,
            "calcola": 4.5,
            "dimostra": 5.0,
            "algoritmo": 5.0,
            "risolvi": 4.5,
        }

    def _compute_logits(self, query: str):
        tokens = [t.lower() for t in re.findall(r"\w+", query)]
        logits = {
            "conversation": 0.5,
            "action_direct": 0.5,
            "whiteboard_canvas": 0.5,
            "browser_action": 0.5,
            "complex_task": 0.5,
        }
        target_agent = None
        direct_action = None
        surface_action = None
        params = {}

        has_whiteboard = any(t in self._whiteboard_tokens for t in tokens)
        has_browser = any(t in self._browser_tokens for t in tokens)
        has_chitchat = any(t in self._chitchat_tokens for t in tokens)

        for token in tokens:
            if token in self._chitchat_tokens:
                logits["conversation"] += self._chitchat_tokens[token]
            if token in self._whiteboard_tokens:
                logits["whiteboard_canvas"] += self._whiteboard_tokens[token]
            if token in self._browser_tokens:
                logits["browser_action"] += self._browser_tokens[token]
            if token in self._action_tokens:
                agent, action, score = self._action_tokens[token]
                if not has_whiteboard and not has_browser:
                    logits["action_direct"] += score
                    if target_agent is None:
                        target_agent = agent
                        direct_action = action
            if token in self._complex_tokens:
                logits["complex_task"] += self._complex_tokens[token]

        if has_whiteboard:
            logits["action_direct"] = 0.5
            target_agent = "whiteboard"
            direct_action = "open_whiteboard"
            surface_action = "collaborative_canvas"
        elif has_browser:
            logits["action_direct"] = 0.5
            target_agent = "browser_agent"
            direct_action = "navigate_web"
            surface_action = "browser_surface"
        elif has_chitchat and logits["conversation"] > logits["action_direct"] and logits["conversation"] > logits["complex_task"]:
            target_agent = "atena_conversation"
            direct_action = "chat_reply"
            surface_action = "dialogue_surface"

        if len(tokens) > 20:
            logits["complex_task"] += min(float(len(tokens) - 20) * 0.15, 3.5)
        elif len(tokens) <= 6 and logits["action_direct"] > 2.0:
            logits["action_direct"] += 2.0

        if target_agent:
            params["raw_tokens"] = tokens
            params["detected_agent"] = target_agent
            params["action"] = direct_action

        return logits, target_agent, direct_action, surface_action, params

    @staticmethod
    def _softmax(logits: Dict[str, float]) -> Dict[str, float]:
        max_z = max(logits.values())
        exp_vals = {k: math.exp(v - max_z) for k, v in logits.items()}
        total = sum(exp_vals.values())
        return {k: v / total for k, v in exp_vals.items()}

    def classify_sync(self, query: str) -> System1Decision:
        t0 = time.perf_counter()
        logits, target_agent, direct_action, surface_action, params = self._compute_logits(query)
        probs = self._softmax(logits)

        best_key = max(probs, key=probs.get)
        intent = System1Intent(best_key)
        confidence = round(probs[best_key], 4)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return System1Decision(
            intent=intent,
            confidence=confidence,
            latency_ms=round(elapsed_ms, 3),
            logits={k: round(v, 3) for k, v in logits.items()},
            target_agent=target_agent,
            direct_action=direct_action,
            surface_action=surface_action,
            parameters=params,
        )

    async def classify(self, query: str) -> System1Decision:
        return self.classify_sync(query)

system1_router = System1Router()
