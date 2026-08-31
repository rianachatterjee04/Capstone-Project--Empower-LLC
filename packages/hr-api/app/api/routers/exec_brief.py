"""Executive brief router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.exec_brief_service import build_brief


router = APIRouter(prefix="/exec-brief", tags=["exec-brief"])


@router.get("/today")
async def today(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    brief = await build_brief(db, actor.org_id)
    return brief.to_dict()
