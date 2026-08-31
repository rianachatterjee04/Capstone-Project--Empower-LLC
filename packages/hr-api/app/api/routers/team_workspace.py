"""Team operating workspaces router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.team_workspace_service import (
    build_workspace,
    find_team,
    list_teams,
    teams_summary,
)


router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("")
async def list_(actor: Actor = Depends(require_org)):
    return {"items": list_teams()}


@router.get("/summary")
async def summary(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    return {"items": await teams_summary(db, actor.org_id)}


@router.get("/{slug}")
async def workspace(slug: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    name = find_team(slug)
    if not name:
        raise HTTPException(status_code=404, detail="Team not found")
    return await build_workspace(db, actor.org_id, name)
