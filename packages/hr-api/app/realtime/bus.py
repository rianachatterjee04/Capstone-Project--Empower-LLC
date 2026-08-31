"""Org-scoped realtime event bus.

SECURITY HISTORY — why this is keyed by org_id
----------------------------------------------
This module previously held a single process-global `subscribers: Set[WebSocket]`
and a `publish(event, payload)` that fanned every event out to every connected
socket with no tenant filter. Combined with the unauthenticated `/ws` endpoint
that fed it, that meant:

  * any anonymous caller could connect and receive EVERY tenant's HR events —
    case decisions, candidate movements, comp actions, investigation workflow
    transitions; and
  * `POST /ws/test-broadcast` let any anonymous caller inject arbitrary events
    into every connected client.

`/ws` now requires a token and resolves the caller's org (see app/api/realtime_ws.py).
This bus enforces the other half: delivery is per-org, and an event that cannot be
attributed to an org is DROPPED rather than broadcast.

FAIL-CLOSED. `publish()` takes an explicit `org_id`. When it is None the event is
logged and discarded. That is deliberate: the previous behaviour — broadcast to
everyone when scoping is unknown — is exactly the bug. A dropped notification is a
missing UI refresh; a mis-delivered one is a cross-tenant data leak.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("foundry.realtime")

# org_id -> set of sockets belonging to that org.
_connections: Dict[str, Set[WebSocket]] = {}


def register(org_id: str, ws: WebSocket) -> None:
    _connections.setdefault(org_id, set()).add(ws)


def unregister(org_id: Optional[str], ws: WebSocket) -> None:
    if not org_id:
        # Defensive: drop the socket from every bucket rather than leaking it.
        for peers in _connections.values():
            peers.discard(ws)
        return
    peers = _connections.get(org_id)
    if peers is None:
        return
    peers.discard(ws)
    if not peers:
        _connections.pop(org_id, None)


def connection_count(org_id: str) -> int:
    return len(_connections.get(org_id, ()))


def _extract_org_id(payload: Any) -> Optional[str]:
    """Best-effort org extraction from a publisher's payload.

    Several publishers pass a nested result dict rather than a flat payload, so
    look one level down as well. Returns None when the org cannot be determined,
    which causes publish() to drop the event.
    """
    if not isinstance(payload, dict):
        return None
    for key in ("org_id", "organization_id"):
        val = payload.get(key)
        if val:
            return str(val)
    for nested_key in ("payload", "result", "data"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            for key in ("org_id", "organization_id"):
                val = nested.get(key)
                if val:
                    return str(val)
    return None


async def publish(event: str, payload: dict, org_id: Optional[str] = None) -> None:
    """Deliver `event` to the sockets of ONE org.

    org_id may be passed explicitly (preferred) or inferred from the payload. If
    neither yields an org the event is dropped — see the module docstring.
    """
    target = org_id or _extract_org_id(payload)
    if not target:
        logger.warning(
            "realtime: dropping event %r — no org_id on the payload and none "
            "supplied by the caller. Events are delivered per-org; an "
            "unattributable event is never broadcast.",
            event,
        )
        return

    peers = _connections.get(target)
    if not peers:
        return

    message = json.dumps({"event": event, "data": payload})
    dead = []
    for ws in peers:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        unregister(target, ws)
