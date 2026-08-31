"""Workforce execution layer router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.tasks_service import (
    create_task,
    link_task_to_kr,
    list_tasks,
    orchestrate_onboarding,
    orchestrate_review_cycle,
    projects_overview,
    tasks_for_key_result,
    tasks_summary,
    update_task,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def list_(
    status: str | None = None,
    owner_role: str | None = None,
    source: str | None = None,
    department: str | None = None,
    project: str | None = None,
    employee_id: str | None = None,
    owner_name: str | None = None,
    actor: Actor = Depends(require_org),
):
    return {
        "items": list_tasks(
            actor.org_id,
            status=status,
            owner_role=owner_role,
            source=source,
            department=department,
            project=project,
            employee_id=employee_id,
            owner_name=owner_name,
        )
    }


@router.get("/summary")
async def summary(actor: Actor = Depends(require_org)):
    return tasks_summary(actor.org_id)


@router.get("/projects")
async def projects(actor: Actor = Depends(require_org)):
    return {"items": projects_overview(actor.org_id)}


@router.post("")
async def create(payload: dict, actor: Actor = Depends(require_org)):
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="title required")
    payload.setdefault("assigned_by_id", actor.user_id)
    payload.setdefault("assigned_by_name", actor.claims.get("email") or actor.user_id)
    return create_task(actor.org_id, payload)


@router.patch("/{task_id}")
async def patch(task_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = update_task(actor.org_id, task_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="Task not found")
    return out


@router.post("/orchestrate/onboarding")
async def orchestrate_onboarding_route(payload: dict, actor: Actor = Depends(require_org)):
    name = payload.get("employee_name")
    role = payload.get("role")
    if not name or not role:
        raise HTTPException(status_code=400, detail="employee_name and role required")
    return {
        "items": orchestrate_onboarding(
            actor.org_id,
            name,
            role,
            manager_name=payload.get("manager_name") or "Manager",
        )
    }


@router.post("/orchestrate/review-cycle")
async def orchestrate_review_route(payload: dict, actor: Actor = Depends(require_org)):
    cycle = payload.get("cycle_name") or "Q2 review cycle"
    return {"items": orchestrate_review_cycle(actor.org_id, cycle)}


@router.get("/by-key-result/{kr_id}")
async def by_key_result(kr_id: str, actor: Actor = Depends(require_org)):
    return {"items": tasks_for_key_result(actor.org_id, kr_id)}


@router.post("/{task_id}/link-kr")
async def link_kr(task_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = link_task_to_kr(
        actor.org_id,
        task_id,
        payload.get("objective_id"),
        payload.get("key_result_id"),
    )
    if not out:
        raise HTTPException(status_code=404, detail="Task not found")
    return out
