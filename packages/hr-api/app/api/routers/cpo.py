"""CPO Command Center router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.cpo_service import build_report


router = APIRouter(prefix="/cpo", tags=["cpo"])


@router.get("/report")
async def report(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    rep = await build_report(db, actor.org_id)
    return rep.to_dict()
