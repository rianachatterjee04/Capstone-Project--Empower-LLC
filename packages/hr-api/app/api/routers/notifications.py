"""Notifications router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.notifications_service import (
    list_notifications,
    mark_all_read,
    mark_read,
    push,
    snooze,
)


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_(
    topic: str | None = None,
    unread_only: bool = False,
    actor: Actor = Depends(require_org),
):
    return list_notifications(actor.org_id, topic=topic, unread_only=unread_only)


@router.post("/{notif_id}/read")
async def read(notif_id: str, actor: Actor = Depends(require_org)):
    out = mark_read(actor.org_id, notif_id, True)
    if not out:
        raise HTTPException(status_code=404, detail="Notification not found")
    return out


@router.post("/{notif_id}/unread")
async def unread(notif_id: str, actor: Actor = Depends(require_org)):
    out = mark_read(actor.org_id, notif_id, False)
    if not out:
        raise HTTPException(status_code=404, detail="Notification not found")
    return out


@router.post("/read-all")
async def read_all(actor: Actor = Depends(require_org)):
    n = mark_all_read(actor.org_id)
    return {"marked_read": n}


@router.post("/{notif_id}/snooze")
async def snooze_(notif_id: str, payload: dict, actor: Actor = Depends(require_org)):
    hours = int(payload.get("hours") or 24)
    out = snooze(actor.org_id, notif_id, hours=hours)
    if not out:
        raise HTTPException(status_code=404, detail="Notification not found")
    return out


@router.post("")
async def push_(payload: dict, actor: Actor = Depends(require_org)):
    return push(actor.org_id, payload)
