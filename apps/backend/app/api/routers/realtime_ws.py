from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import json

from app.core.security import decode_supabase_jwt, get_actor_from_claims

router = APIRouter(tags=["realtime"])

# ---------------------------------------------------------
# In-memory connection registry
# (Later you can replace with Redis pub/sub)
# ---------------------------------------------------------
connections: Dict[str, Set[WebSocket]] = {}


# ---------------------------------------------------------
# Register connection
# ---------------------------------------------------------
async def register(org_id: str, ws: WebSocket):
    if org_id not in connections:
        connections[org_id] = set()
    connections[org_id].add(ws)


# ---------------------------------------------------------
# Unregister connection
# ---------------------------------------------------------
async def unregister(org_id: str, ws: WebSocket):
    if org_id in connections:
        connections[org_id].discard(ws)
        if not connections[org_id]:
            del connections[org_id]


# ---------------------------------------------------------
# Broadcast event to org
# (Called by workflows / push hooks / services)
# ---------------------------------------------------------
async def broadcast(org_id: str, event: dict):
    if org_id not in connections:
        return

    dead = []
    for ws in connections[org_id]:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)

    for ws in dead:
        await unregister(org_id, ws)


# ---------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------
@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):

    await ws.accept()
    org_id = None

    try:
        token = ws.query_params.get("token")
        if not token:
            await ws.send_json({"error": "missing_token"})
            await ws.close()
            return

        claims = decode_supabase_jwt(token)
        actor = get_actor_from_claims(claims)

        org_id = actor.get("org_id")
        role = actor.get("role")

        if not org_id:
            await ws.send_json({"error": "invalid_token"})
            await ws.close()
            return

        await register(org_id, ws)

        await ws.send_json({
            "type": "connected",
            "org_id": org_id,
            "role": role
        })

        # -------------------------------------------------
        # Listen for client subscriptions / pings
        # -------------------------------------------------
        while True:
            data = await ws.receive_text()

            if data == "ping":
                await ws.send_text("pong")
                continue

            try:
                msg = json.loads(data)
            except Exception:
                continue

            # client requests manual subscribe (future filtering)
            if msg.get("type") == "subscribe":
                await ws.send_json({"type": "subscribed", "channel": msg.get("channel")})

    except WebSocketDisconnect:
        pass

    finally:
        if org_id:
            await unregister(org_id, ws)

