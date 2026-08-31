"""Approvals Center router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.approvals_service import list_approvals


router = APIRouter(prefix="/approvals-center", tags=["approvals-center"])


@router.get("")
async def index(kind: str | None = None, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    return await list_approvals(db, actor.org_id, kind=kind)
