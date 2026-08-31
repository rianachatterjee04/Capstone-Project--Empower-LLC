"""Public profile router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.public_profile_service import (
    get_profile,
    list_profiles,
    update_profile,
)


router = APIRouter(prefix="/public-profile", tags=["public-profile"])


@router.get("")
async def directory(actor: Actor = Depends(require_org)):
    return {"items": await list_profiles(actor.org_id)}


@router.get("/{employee_id}")
async def get(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    out = await get_profile(db, actor.org_id, employee_id)
    if not out:
        raise HTTPException(status_code=404, detail="Profile not found")
    return out


@router.patch("/{employee_id}")
async def patch(employee_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    out = await update_profile(db, actor.org_id, employee_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="Profile not found")
    return out
