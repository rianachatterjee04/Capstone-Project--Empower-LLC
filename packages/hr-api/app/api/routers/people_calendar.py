"""People-ops calendar router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.calendar_service import upcoming


router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("")
async def index(
    days: int = 30,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    return await upcoming(db, actor.org_id, days=max(7, min(120, days)))
