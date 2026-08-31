"""Narrative analytics router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.narrative_analytics_service import build


router = APIRouter(prefix="/narrative-analytics", tags=["narrative-analytics"])


@router.get("")
async def index(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    return await build(db, actor.org_id)
