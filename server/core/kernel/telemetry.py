import json
import time
import asyncio
from typing import Any, Dict
from server.config.env import settings

class NeuralTelemetry:
    @staticmethod
    async def emit(event_type: str, agent_id: str, payload: Dict[str, Any]) -> None:
        try:
            event = {
                "type": "telemetry",
                "sub_type": event_type,
                "agent_id": agent_id,
                "timestamp": time.time(),
                "payload": payload
            }
            # I/O asincrono fire-and-forget per non bloccare l'esecuzione (Zero-Trust/Fail-Safe)
            asyncio.create_task(NeuralTelemetry._write_to_bus(event))
        except Exception:
            pass 

    @staticmethod
    async def _write_to_bus(event: Dict[str, Any]) -> None:
        try:
            # Socket stream mock per bus-core websocket broadcaster
            with open(settings.SANDBOX_SOCKET_PATH + "_telemetry.sock", "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except OSError:
            pass
