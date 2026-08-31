"""Activity timeline router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.activity_service import feed


router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/feed")
async def activity_feed(
    kind: str | None = None,
    limit: int = 60,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    return await feed(db, actor.org_id, kind=kind, limit=max(10, min(200, limit)))
