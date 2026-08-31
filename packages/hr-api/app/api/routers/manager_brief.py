"""Manager OS — daily brief router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.manager_brief_service import build_brief, list_managers


router = APIRouter(prefix="/manager-brief", tags=["manager-brief"])


@router.get("/managers")
async def managers(actor: Actor = Depends(require_org)):
    return {"items": list_managers()}


@router.get("/today")
async def today(
    manager: str | None = None,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    brief = await build_brief(db, actor.org_id, manager or list_managers()[0]["name"])
    return brief.to_dict()
