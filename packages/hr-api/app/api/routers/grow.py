"""Grow router — career ladders, competencies, and employee growth plans.

Thin router over grow_service (in-process, org-scoped), mirroring the goals.py /
calibration.py pattern.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services import grow_service as svc


router = APIRouter(prefix="/grow", tags=["grow"])

_ADMIN = ("owner", "admin", "hr", "manager")


# --- Ladders ----------------------------------------------------------------
@router.get("/ladders")
async def list_ladders(actor: Actor = Depends(require_org)):
    return svc.list_ladders(actor.org_id)


@router.get("/ladders/{ladder_id}")
async def get_ladder(ladder_id: str, actor: Actor = Depends(require_org)):
    out = svc.get_ladder(actor.org_id, ladder_id)
    if not out:
        raise HTTPException(status_code=404, detail="Ladder not found")
    return out


@router.post("/ladders")
async def create_ladder(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.create_ladder(actor.org_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="family required")
    return out


@router.post("/ladders/{ladder_id}/levels")
async def add_level(ladder_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.add_level(actor.org_id, ladder_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="name required or ladder not found")
    return out


@router.post("/ladders/{ladder_id}/competencies")
async def add_competency(ladder_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.add_competency(actor.org_id, ladder_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="name required or ladder not found")
    return out


@router.post("/ladders/{ladder_id}/expectations")
async def set_expectation(ladder_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.set_expectation(actor.org_id, ladder_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="competency_id and level_id required")
    return out


# --- Growth plans -----------------------------------------------------------
@router.get("/plans")
async def list_plans(employee_id: str | None = None, actor: Actor = Depends(require_org)):
    return svc.list_plans(actor.org_id, employee_id=employee_id)


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, actor: Actor = Depends(require_org)):
    out = svc.get_plan(actor.org_id, plan_id)
    if not out:
        raise HTTPException(status_code=404, detail="Plan not found")
    return out


@router.post("/plans")
async def create_plan(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.create_plan(actor.org_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="employee_id and valid ladder_id required")
    return out


@router.patch("/plans/{plan_id}")
async def update_plan(plan_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = svc.update_plan(actor.org_id, plan_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="Plan not found")
    return out


@router.post("/plans/{plan_id}/ratings")
async def set_rating(plan_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = svc.set_rating(actor.org_id, plan_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="competency_id required or plan not found")
    return out


@router.post("/plans/{plan_id}/growth-goals")
async def add_growth_goal(plan_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = svc.add_growth_goal(actor.org_id, plan_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="text required or plan not found")
    return out


@router.post("/plans/{plan_id}/link")
async def link_plan(plan_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = svc.link_plan(actor.org_id, plan_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="Plan not found")
    return out


@router.get("/plans/{plan_id}/gap")
async def gap_view(plan_id: str, actor: Actor = Depends(require_org)):
    out = svc.gap_view(actor.org_id, plan_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Plan or ladder not found")
    return out


# --- AI assist (fail-soft) --------------------------------------------------
@router.post("/plans/{plan_id}/suggest-actions")
async def suggest_actions(plan_id: str, actor: Actor = Depends(require_org)):
    out = svc.suggest_actions(actor.org_id, plan_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return out
