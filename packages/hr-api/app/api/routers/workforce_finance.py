"""Workforce Finance router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.workforce_finance_service import (
    comp_budget,
    forecast,
    hiring_impact,
    overview,
)


router = APIRouter(prefix="/workforce-finance", tags=["workforce-finance"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "manager")


@router.get("/overview")
async def overview_route(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await overview(db, actor.org_id)


@router.get("/forecast")
async def forecast_route(
    months: int = 12,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await forecast(db, actor.org_id, months=max(3, min(24, months)))


@router.get("/hiring-impact")
async def hiring_route(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await hiring_impact(db, actor.org_id)


@router.get("/comp-budget")
async def comp_budget_route(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await comp_budget(db, actor.org_id)
