from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from app.services.benefits_opt import run_optimizer

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.core.json_utils import json_safe
from app.services.benefits_opt import optimize_benefits

router = APIRouter(prefix="/benefits", tags=["benefits"])


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


@router.post("/plans")
async def create_plan(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)

    res = await db.execute(
        text("""
            insert into public.benefit_plans(
                org_id,
                name,
                provider,
                category,
                employer_cost,
                employee_cost,
                metadata,
                created_at
            )
            values(
                :org_id,
                :name,
                :provider,
                :category,
                :employer_cost,
                :employee_cost,
                cast(:metadata as jsonb),
                now()
            )
            returning *
        """),
        {
            "org_id": org_id,
            "name": payload.get("name"),
            "provider": payload.get("provider"),
            "category": payload.get("category"),
            "employer_cost": payload.get("employer_cost", 0),
            "employee_cost": payload.get("employee_cost", 0),
            "metadata": json.dumps(json_safe(payload.get("metadata", {}))),
        },
    )

    row = res.mappings().first()
    row_dict = json_safe(dict(row)) if row else None

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="benefit_plan.created",
            entity_type="benefit_plan",
            entity_id=as_uuid(row_dict["id"]) if row_dict else None,
            payload=row_dict or {},
        )
    )

    await db.commit()
    return row_dict


@router.get("/plans")
async def list_plans(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)

    res = await db.execute(
        text("""
            select *
            from public.benefit_plans
            where org_id = :org_id
            order by created_at desc
        """),
        {"org_id": org_id},
    )

    rows = res.mappings().all()
    return [json_safe(dict(r)) for r in rows]


@router.post("/enrollment-window")
async def create_enrollment_window(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)

    res = await db.execute(
        text("""
            insert into public.benefit_enrollment_windows(
                org_id,
                start_date,
                end_date,
                fiscal_year,
                created_at
            )
            values(
                :org_id,
                :start_date,
                :end_date,
                :fiscal_year,
                now()
            )
            returning *
        """),
        {
            "org_id": org_id,
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "fiscal_year": payload.get("fiscal_year"),
        },
    )

    row = res.mappings().first()
    row_dict = json_safe(dict(row)) if row else None
    await db.commit()
    return row_dict


@router.post("/enroll")
async def enroll(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)

    employee_id = payload.get("employee_id")
    plan_id = payload.get("plan_id")

    if not employee_id or not plan_id:
        raise HTTPException(status_code=400, detail="employee_id and plan_id required")

    res = await db.execute(
        text("""
            insert into public.employee_benefit_elections(
                org_id,
                employee_id,
                plan_id,
                elected_on,
                created_at
            )
            values(
                :org_id,
                :employee_id,
                :plan_id,
                current_date,
                now()
            )
            returning *
        """),
        {
            "org_id": org_id,
            "employee_id": as_uuid(employee_id),
            "plan_id": as_uuid(plan_id),
        },
    )

    row = res.mappings().first()
    row_dict = json_safe(dict(row)) if row else None
    await db.commit()
    return row_dict


@router.post("/life-event")
async def life_event(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)

    employee_id = payload.get("employee_id")
    event_type = payload.get("event_type")
    event_date = payload.get("event_date")

    if not employee_id or not event_type or not event_date:
        raise HTTPException(status_code=400, detail="employee_id, event_type, event_date required")

    res = await db.execute(
        text("""
            insert into public.benefit_life_events(
                org_id,
                employee_id,
                event_type,
                event_date,
                metadata,
                created_at
            )
            values(
                :org_id,
                :employee_id,
                :event_type,
                :event_date,
                cast(:metadata as jsonb),
                now()
            )
            returning *
        """),
        {
            "org_id": org_id,
            "employee_id": as_uuid(employee_id),
            "event_type": event_type,
            "event_date": event_date,
            "metadata": json.dumps(json_safe(payload.get("metadata", {}))),
        },
    )

    row = res.mappings().first()
    row_dict = json_safe(dict(row)) if row else None
    await db.commit()
    return row_dict


@router.post("/optimize")
async def optimize(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    fiscal_year = payload.get("fiscal_year")
    budget = payload.get("budget")

    if fiscal_year is None or budget is None:
        raise HTTPException(status_code=400, detail="fiscal_year and budget required")

    result = await optimize_benefits(db, org_id, fiscal_year, budget)
    safe_result = json_safe(result)

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="benefits.optimized",
            entity_type="benefit_optimization_run",
            entity_id=as_uuid(safe_result.get("id")) if isinstance(safe_result, dict) and safe_result.get("id") else None,
            payload=safe_result,
        )
    )

    await db.commit()
    return safe_result


@router.get("/optimization-runs")
async def list_optimization_runs(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)

    res = await db.execute(
        text("""
            select *
            from public.benefit_optimization_runs
            where org_id = :org_id
            order by created_at desc nulls last, id desc
        """),
        {"org_id": org_id},
    )

    rows = res.mappings().all()
    return [json_safe(dict(r)) for r in rows]
