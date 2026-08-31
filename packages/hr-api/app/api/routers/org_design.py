"""AI Org Design router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.org_design_service import analyze


router = APIRouter(prefix="/org-design", tags=["org-design"])


@router.get("/analyze")
async def run(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = await analyze(db, actor.org_id)
    return out.to_dict()
