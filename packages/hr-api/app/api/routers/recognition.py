"""Recognition router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.recognition_service import (
    list_recognitions,
    post_recognition,
    react,
)


router = APIRouter(prefix="/recognition", tags=["recognition"])


@router.get("")
async def index(
    value: str | None = None,
    to_name: str | None = None,
    actor: Actor = Depends(require_org),
):
    return list_recognitions(actor.org_id, value=value, to_name=to_name)


@router.post("")
async def create(payload: dict, actor: Actor = Depends(require_org)):
    from_name = payload.get("from_name") or actor.claims.get("email") or "Internal"
    out = post_recognition(actor.org_id, payload, from_name=from_name)
    if not out:
        raise HTTPException(status_code=400, detail="to_name and body required")
    return out


@router.post("/{rec_id}/react")
async def react_(rec_id: str, payload: dict, actor: Actor = Depends(require_org)):
    emoji = payload.get("emoji") or "❤"
    by = payload.get("by") or actor.claims.get("email") or "You"
    out = react(actor.org_id, rec_id, emoji=emoji, by_name=by)
    if not out:
        raise HTTPException(status_code=404, detail="Recognition not found")
    return out
