"""Skills Graph router."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.skills_graph_service import compute_graph

router = APIRouter(prefix="/skills-graph", tags=["skills-graph"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager", "employee")


@router.get("")
async def graph(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await compute_graph(db, UUID(actor.org_id))
