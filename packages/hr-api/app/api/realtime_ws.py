"""Authenticated, org-scoped realtime WebSocket.

SECURITY HISTORY
----------------
This endpoint previously called `await ws.accept()` with no token and added the
socket to a process-global subscriber set, so any anonymous caller received every
tenant's HR events. It also exposed `POST /ws/test-broadcast`, unauthenticated,
which let anyone inject arbitrary events into every connected client.

A correct org-scoped implementation already existed at
`app/api/routers/realtime_ws.py` but was never mounted — `app/main.py` imported
this module instead. Rather than swap the mount (which would have silently
detached every publisher, since they write to `app/realtime/bus.py` and that other
module keeps its own registry), this module is now the authenticated one and
delegates connection state to the bus, so publishers and subscribers share a
single org-keyed registry.

Auth: the browser WebSocket API cannot set headers, so the token is passed as a
query parameter — standard for WS. It is verified with the same Supabase decoder
the HTTP routes use; an absent, malformed, or org-less token is refused before the
socket joins any registry.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import Actor, require_org
from app.core.security import decode_supabase_jwt, get_actor_from_claims
from app.realtime import bus

router = APIRouter()
logger = logging.getLogger("foundry.realtime")


@router.websocket("/ws")
async def realtime_socket(ws: WebSocket):
    """One realtime channel per ORG — hiring, onboarding, reviews, escalations,
    approvals, org changes. A client only ever receives its own org's events."""
    await ws.accept()

    org_id = None
    try:
        token = ws.query_params.get("token")
        if not token:
            await ws.send_json({"error": "missing_token"})
            await ws.close(code=1008)
            return

        try:
            actor = get_actor_from_claims(decode_supabase_jwt(token))
        except Exception:
            # Do not echo the decode error — it can disclose whether a token is
            # merely expired vs structurally invalid.
            await ws.send_json({"error": "invalid_token"})
            await ws.close(code=1008)
            return

        org_id = actor.get("org_id")
        if not org_id:
            await ws.send_json({"error": "invalid_token"})
            await ws.close(code=1008)
            return

        bus.register(org_id, ws)
        await ws.send_json({"type": "connected", "org_id": org_id,
                            "role": actor.get("role")})
        logger.info("WebSocket connected org=%s", org_id)

        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
                continue
            try:
                msg = json.loads(data)
            except Exception:
                continue
            if msg.get("type") == "subscribe":
                await ws.send_json({"type": "subscribed",
                                    "channel": msg.get("channel")})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket error org=%s: %s", org_id, exc)
    finally:
        bus.unregister(org_id, ws)


@router.post("/ws/test-broadcast")
async def test_broadcast(payload: dict, actor: Actor = Depends(require_org)):
    """Broadcast into the CALLER'S org only.

    Previously unauthenticated and un-scoped, so any anonymous caller could inject
    events into every connected client of every tenant. The org is now taken from
    the authenticated actor and cannot be chosen by the caller.
    """
    await bus.publish("decision", payload, org_id=actor.org_id)
    return {"ok": True, "org_id": actor.org_id,
            "connections": bus.connection_count(actor.org_id)}
