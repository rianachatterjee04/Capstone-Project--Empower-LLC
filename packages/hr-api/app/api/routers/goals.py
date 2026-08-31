"""Goals & OKRs router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.goals_service import create_objective, list_objectives, update_key_result


router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("")
async def index(
    cycle: str | None = None,
    team: str | None = None,
    owner: str | None = None,
    actor: Actor = Depends(require_org),
):
    return list_objectives(actor.org_id, cycle=cycle, team=team, owner=owner)


@router.post("")
async def create(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="title required")
    return create_objective(actor.org_id, payload)


@router.patch("/{objective_id}/key-results/{kr_id}")
async def patch_kr(objective_id: str, kr_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = update_key_result(actor.org_id, objective_id, kr_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="Objective / key result not found")
    return out
