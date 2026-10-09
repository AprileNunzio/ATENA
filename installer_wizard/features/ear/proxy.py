import asyncio
import logging
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect

import auth
from features.authz.heard import heard

logger = logging.getLogger("atena.ear.proxy")
UPSTREAM = "ws://127.0.0.1:8093"
MAX_MESSAGE = 2 ** 22
DENIED = 4401


def _node_allowed(socket: WebSocket) -> bool:
    node_id = socket.headers.get("x-atena-node", "")
    if not node_id:
        return False
    from features.nodes.registry import registry
    try:
        registry.authenticate(node_id, socket.headers.get("authorization", "").removeprefix("Bearer ").strip())
    except PermissionError:
        return False
    return True


def allowed(socket: WebSocket) -> bool:
    peer = socket.client.host if socket.client else ""
    return (peer in ("127.0.0.1", "::1", "localhost") or bool(auth.verify(socket.cookies.get(auth.SESSION_COOKIE)))
            or _node_allowed(socket))


async def _up(client: Any, upstream: Any) -> None:
    while True:
        message = await client.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes") is not None:
            await upstream.send(message["bytes"])
        elif message.get("text") is not None:
            await upstream.send(message["text"])


async def _down(client: Any, upstream: Any, device: str) -> None:
    async for message in upstream:
        if isinstance(message, bytes):
            await client.send_bytes(message)
        else:
            heard.tap(message, device)
            await client.send_text(message)


def device_of(socket: Any) -> str:
    node_id = socket.headers.get("x-atena-node", "") if hasattr(socket, "headers") else ""
    return f"node:{node_id}" if node_id and _node_allowed(socket) else "mic:local"


async def pump(client: Any, upstream: Any, device: str = "mic:local") -> None:
    tasks = [asyncio.create_task(_up(client, upstream)), asyncio.create_task(_down(client, upstream, device))]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def proxy(socket: WebSocket) -> None:
    if not allowed(socket):
        await socket.close(code=DENIED)
        return
    await socket.accept()
    try:
        async with websockets.connect(UPSTREAM, max_size=MAX_MESSAGE) as upstream:
            await pump(socket, upstream, device_of(socket))
    except (OSError, websockets.WebSocketException, WebSocketDisconnect, RuntimeError) as exc:
        logger.info("ear proxy closed: %s", exc)
    try:
        await socket.close()
    except RuntimeError:
        return
