from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json
from datetime import date, datetime, timedelta

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.services.benefits_opt import run_optimizer
from app.workflow.engine import engine

router = APIRouter(prefix="/benefits", tags=["benefits"])


# ============================================================
# HELPERS
# ============================================================
async def _get_employee_id(actor: Actor, db: AsyncSession, payload: dict):
    if actor.role == "employee":
        row = (await db.execute(text("""
            select id from public.employees
            where org_id=:org_id and user_id=:uid
        """), {"org_id": actor.org_id, "uid": actor.user_id})).first()
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")
        return str(row[0])

    eid = payload.get("employee_id")
    if not eid:
        raise HTTPException(status_code=400, detail="employee_id required")
    return eid


async def _enrollment_open(db: AsyncSession, org_id: str):
    today = date.today()
    row = (await db.execute(text("""
        select start_date, end_date
        from public.benefit_enrollment_windows
        where org_id=:org_id
        order by start_date desc
        limit 1
    """), {"org_id": org_id})).first()

    if not row:
        return False

    return row[0] <= today <= row[1]


async def _qle_open(db: AsyncSession, org_id: str, employee_id: str):
    """30-day enrollment after qualifying life event"""
    row = (await db.execute(text("""
        select event_date
        from public.benefit_life_events
        where org_id=:org_id and employee_id=:eid
        order by event_date desc
        limit 1
    """), {"org_id": org_id, "eid": employee_id})).first()

    if not row:
        return False

    return date.today() <= (row[0] + timedelta(days=30))


# ============================================================
# CREATE BENEFIT PLAN (HR)
# ============================================================
@router.post("/plans")
async def create_plan(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        insert into public.benefit_plans(
            org_id, name, type,
            employer_monthly_cost,
            employee_monthly_cost,
            metadata
        )
        values (:org_id, :name, :type, :employer, :employee, :meta::jsonb)
        returning id
    """), {
        "org_id": actor.org_id,
        "name": payload.get("name"),
        "type": payload.get("type", "medical"),
        "employer": payload.get("employer_monthly_cost"),
        "employee": payload.get("employee_monthly_cost"),
        "meta": json.dumps(payload.get("metadata", {})),
    })

    pid = res.first()[0]

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="benefit_plan.created",
        entity_type="benefit_plan",
        entity_id=pid,
        payload=payload
    ))

    await db.commit()
    return {"id": str(pid)}


# ============================================================
# ENROLLMENT WINDOW (HR)
# ============================================================
@router.post("/enrollment-window")
async def create_window(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        insert into public.benefit_enrollment_windows(org_id,start_date,end_date,fiscal_year)
        values (:org_id,:start,:end,:fy)
    """), {
        "org_id": actor.org_id,
        "start": payload["start_date"],
        "end": payload["end_date"],
        "fy": payload["fiscal_year"]
    })

    await db.commit()
    return {"ok": True}


# ============================================================
# ENROLL (ENFORCES OPEN ENROLLMENT + QLE)
# ============================================================
@router.post("/enroll")
async def enroll(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    employee_id = await _get_employee_id(actor, db, payload)

    open_enrollment = await _enrollment_open(db, actor.org_id)
    qle = await _qle_open(db, actor.org_id, employee_id)

    if not (open_enrollment or qle):
        raise HTTPException(status_code=403, detail="Enrollment window closed")

    await db.execute(text("""
        insert into public.employee_benefit_elections(org_id,employee_id,plan_id,elected_on)
        values (:org_id,:employee_id,:plan_id,now())
        on conflict (org_id,employee_id,plan_id)
        do update set elected_on=now()
    """), {
        "org_id": actor.org_id,
        "employee_id": employee_id,
        "plan_id": payload.get("plan_id")
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="benefits.enrolled",
        entity_type="employee_benefit_election",
        entity_id=None,
        payload=payload
    ))

    await db.commit()

    # trigger payroll recalculation
    engine.trigger("benefits.changed", {"employee_id": employee_id})

    return {"ok": True}


# ============================================================
# QUALIFYING LIFE EVENT
# ============================================================
@router.post("/life-event")
async def life_event(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.benefit_life_events(org_id,employee_id,event_type,event_date,metadata)
        values (:org_id,:eid,:etype,:edate,:meta::jsonb)
    """), {
        "org_id": actor.org_id,
        "eid": payload.get("employee_id"),
        "etype": payload.get("type"),
        "edate": payload.get("date"),
        "meta": json.dumps(payload.get("metadata", {}))
    })

    await db.commit()

    # unlock temporary enrollment workflow
    engine.trigger("benefits.qle_opened", {"employee_id": payload.get("employee_id")})

    return {"ok": True}


# ============================================================
# AI OPTIMIZATION
# ============================================================
@router.post("/optimize")
async def optimize(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    result = await run_optimizer(db, UUID(actor.org_id), int(payload["fiscal_year"]), float(payload["budget"]))

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="benefits.optimized",
        entity_type="benefit_optimization_run",
        entity_id=None,
        payload=result
    ))

    await db.commit()
    return result


# ============================================================
# LISTING
# ============================================================
@router.get("/plans")
async def list_plans(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    res = await db.execute(text("select * from public.benefit_plans where org_id=:org_id order by created_at desc"), {"org_id": actor.org_id})
    cols = res.keys()
    return [dict(zip(cols,row)) for row in res.fetchall()]

