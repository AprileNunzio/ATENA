import asyncio
import time

MAX_PENDING = 8
ACTION_TTL = 120.0


class Inbox:
    def __init__(self) -> None:
        self._items: dict[str, list[dict]] = {}
        self._events: dict[str, asyncio.Event] = {}

    def push(self, node_id: str, action: dict) -> None:
        queue = [a for a in self._items.get(node_id, []) if time.time() - a["at"] < ACTION_TTL]
        self._items[node_id] = (queue + [{**action, "at": time.time()}])[-MAX_PENDING:]
        self._events.setdefault(node_id, asyncio.Event()).set()

    def take(self, node_id: str) -> list[dict]:
        items = [{k: v for k, v in a.items() if k != "at"} for a in self._items.pop(node_id, [])
                 if time.time() - a["at"] < ACTION_TTL]
        event = self._events.get(node_id)
        if event:
            event.clear()
        return items

    async def wait(self, node_id: str, timeout: float) -> list[dict]:
        if not self._items.get(node_id):
            event = self._events.setdefault(node_id, asyncio.Event())
            try:
                await asyncio.wait_for(event.wait(), timeout)
            except asyncio.TimeoutError:
                return []
        return self.take(node_id)


inbox = Inbox()
