"""Workforce risk engine router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.workforce_risk_service import scan


router = APIRouter(prefix="/workforce-risk", tags=["workforce-risk"])


@router.get("/scan")
async def run_scan(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    summary = await scan(db, actor.org_id)
    return summary.to_dict()
