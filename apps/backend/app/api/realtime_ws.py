from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging

# global subscriber registry
from app.realtime.bus import subscribers

router = APIRouter()
logger = logging.getLogger("foundry.realtime")


# =========================================================
# GLOBAL REALTIME CHANNEL
# =========================================================
@router.websocket("/ws")
async def realtime_socket(ws: WebSocket):
    """
    Single realtime channel for the entire HR operating system.

    Everything streams here:
        hiring events
        onboarding progress
        performance reviews
        escalations
        approvals
        org changes
    """

    await ws.accept()
    subscribers.add(ws)

    logger.info("WebSocket connected")

    try:
        while True:
            # keep alive — client can optionally send pings
            await ws.receive_text()

    except WebSocketDisconnect:
        subscribers.discard(ws)
        logger.info("WebSocket disconnected")

    except Exception as e:
        subscribers.discard(ws)
        logger.error(f"WebSocket error: {e}")

