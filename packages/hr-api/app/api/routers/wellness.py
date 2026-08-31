"""Wellness pulse router."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Actor, require_org
from app.services.wellness_service import overview, submit


router = APIRouter(prefix="/wellness", tags=["wellness"])


@router.get("")
async def index(actor: Actor = Depends(require_org)):
    return overview(actor.org_id)


@router.post("/submit")
async def submit_(payload: dict, actor: Actor = Depends(require_org)):
    return submit(actor.org_id, payload)
