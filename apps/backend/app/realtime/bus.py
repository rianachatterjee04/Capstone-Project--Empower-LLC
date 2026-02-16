from __future__ import annotations
from typing import Set
from fastapi import WebSocket
import json
import asyncio

# connected clients
subscribers: Set[WebSocket] = set()


async def publish(event: str, payload: dict):
    """
    Broadcasts system events to all UI clients.
    Called by workflow engine after decisions execute.
    """

    if not subscribers:
        return

    message = json.dumps({
        "event": event,
        "data": payload
    })

    dead = []

    for ws in subscribers:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)

    # cleanup closed sockets
    for ws in dead:
        subscribers.discard(ws)

