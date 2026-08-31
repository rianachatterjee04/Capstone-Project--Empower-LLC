"""Setup wizard router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.setup_wizard_service import build_checklist


router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/checklist")
async def checklist(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    return await build_checklist(db, actor.org_id)
