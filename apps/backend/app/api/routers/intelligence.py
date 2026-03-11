from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.json_utils import json_safe
from sqlalchemy import text
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.intelligence import compensation, performance, workforce

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def require_hr_or_manager(actor: Actor):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")


# ---------------------------------------------------------
# PAY COMPRESSION ANALYSIS
# ---------------------------------------------------------
@router.get("/comp/pay-compression")
async def pay_compression(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    require_hr_or_manager(actor)

    rows = (await db.execute(text("""
        select id, title, level, salary
        from public.employees
        where org_id=:org_id and status='active'
    """), {"org_id": actor.org_id})).mappings().all()

    employees = [dict(r) for r in rows]

    result = compensation.detect_pay_compression(employees)

    # audit WITHOUT sensitive salary output
    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="ai.analysis.pay_compression",
        entity_type="org",
        entity_id=None,
        payload={
            "employee_count": len(employees),
            "issues_found": len(result.get("issues", [])),
            "model": "pay_compression_v1"
        }
    ))

    await db.commit()
    return result


# ---------------------------------------------------------
# RAISE SIMULATOR
# ---------------------------------------------------------
@router.post("/comp/simulate-raise")
async def simulate_raise(employee_id: str, percent: float, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    require_hr_or_manager(actor)

    # guardrails
    if percent < -30 or percent > 50:
        raise HTTPException(status_code=400, detail="Raise percent out of allowed range")

    emp = (await db.execute(text("""
        select id, salary, title, level
        from public.employees
        where id=:id and org_id=:org_id
    """), {"id": employee_id, "org_id": actor.org_id})).mappings().first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    result = compensation.simulate_raise(dict(emp), percent)

    return result


# ---------------------------------------------------------
# PERFORMANCE NARRATIVE
# ---------------------------------------------------------
@router.post("/performance/narrative")
async def narrative(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    is_hr = actor.role in ("owner", "admin", "hr", "manager")

    # employees can only see their own narrative
    if not is_hr:
        row = (await db.execute(text("""
            select id from public.employees
            where org_id=:org_id and user_id=:uid
        """), {"org_id": actor.org_id, "uid": actor.user_id})).first()

        if not row or str(row[0]) != employee_id:
            raise HTTPException(status_code=403, detail="Not allowed")

    review = (await db.execute(text("""
        select self_review, manager_review, ai_flags
        from public.performance_reviews
        where employee_id=:eid and org_id=:org_id
        order by created_at desc limit 1
    """), {"eid": employee_id, "org_id": actor.org_id})).mappings().first()

    if not review:
        raise HTTPException(status_code=404, detail="No review data")

    text_out = performance.write_performance_narrative(dict(review))

    return {
        "narrative": text_out,
        "explainability": "Generated from self review + manager review + discrepancy detection"
    }


# ---------------------------------------------------------
# WORKFORCE FORECAST
# ---------------------------------------------------------
@router.post("/workforce/forecast")
async def forecast(months: int = 12, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    require_hr_or_manager(actor)

    rows = (await db.execute(text("""
        select status, hire_date, termination_date
        from public.employees
        where org_id=:org_id
        limit 20000
    """), {"org_id": actor.org_id})).mappings().all()

    result = workforce.forecast_headcount([dict(r) for r in rows], months)

    return result

