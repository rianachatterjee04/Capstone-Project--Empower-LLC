"""AI Org Graph router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.org_graph_service import build_graph


router = APIRouter(prefix="/org-graph", tags=["org-graph"])


@router.get("")
async def graph(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await build_graph(db, actor.org_id)
