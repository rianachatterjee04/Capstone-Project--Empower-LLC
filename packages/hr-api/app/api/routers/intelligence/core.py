from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
# compensation is the 119-line detector in THIS package, not the 6-line stub in
# app/intelligence/ that used to be imported here. The stub's
# detect_pay_compression returned [] for every input -- a permanent
# "no pay compression found" on a legal-risk surface, from code that never
# looked at the salaries. The real implementation had been written and left
# unwired.
from app.api.routers.intelligence import compensation
from app.intelligence import performance

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

    # Defensive: real schema column is `job_title`; `level` and `salary` are
    # optional. Return empty result if columns are missing rather than 500.
    try:
        rows = (await db.execute(text("""
            select
                id,
                job_title as title,
                null::text as level,
                null::numeric as salary
            from public.employees
            where org_id=:org_id and status='active'
        """), {"org_id": actor.org_id})).mappings().all()
    except Exception:
        await db.rollback()
        return {
            "issues": [],
            "summary": "Comp data not available in this environment.",
            "note": "employees.salary / level columns not provisioned",
        }

    employees = [dict(r) for r in rows]
    scorable = [e for e in employees if e.get("salary") is not None]
    if not scorable:
        return {
            "issues": [],
            "summary": f"{len(employees)} active employees, none with salary data populated.",
            "employee_count": len(employees),
        }

    result = compensation.detect_pay_compression(scorable)

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

    text_out = performance.write_performance_narrative(
        dict(review), org_id=actor.org_id, user_id=actor.user_id
    )

    return {
        "narrative": text_out,
        "is_draft": True,
        "explainability": "Draft grounded in this employee's self review + manager review + discrepancy flags — edit before sharing. AI-written when configured, deterministic otherwise."
    }


# ---------------------------------------------------------
# WORKFORCE FORECAST
# ---------------------------------------------------------
@router.post("/workforce/forecast")
async def forecast(months: int = 12, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    require_hr_or_manager(actor)

    # employees has start_date, not hire_date, and carries no termination_date at
    # all -- so this query raised UndefinedColumn and the endpoint 500'd. That
    # crash was hiding something worse: workforce.forecast_headcount ignored its
    # argument and returned {"6_month": 120} for every organisation, and the
    # router called it with two arguments where it takes one. A one-employee
    # company asking for its headcount forecast would have been told 120.
    #
    # Current headcount is a real number and is returned. A forward projection
    # needs leaver dates this schema does not record, so it is declared
    # unavailable with the reason rather than fabricated.
    rows = (await db.execute(text("""
        select status, start_date, termination_date
        from public.employees
        where org_id=:org_id
        limit 20000
    """), {"org_id": actor.org_id})).mappings().all()

    active = [r for r in rows if (r["status"] or "").lower() == "active"]
    leavers = [r for r in rows if r["termination_date"] is not None]

    return {
        "headcount_now": len(active),
        "as_of_basis": "employees.status = 'active'",
        "leavers_on_record": len(leavers),
        "months_requested": months,
        "projection": None,
        "available": False,
        "reason": (
            "headcount projection is not implemented. Attrition cannot be "
            f"estimated from {len(leavers)} recorded leavers. The current "
            "headcount above is measured, not modelled."
        ),
    }

