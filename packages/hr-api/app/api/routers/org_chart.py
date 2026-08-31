"""Org chart + headcount / attrition reporting.

Built from employees.manager_employee_id (already in the schema; maintained
via /employees/{id}/manager/{mid} and /employee-records/{id}/job-change).

- GET /org-chart/tree       nested reporting tree (visible to whole org)
- GET /org-chart/headcount  by-department counts (hr/manager)
- GET /org-chart/attrition  terminations last 12 months / average headcount

Distinct from /org-graph (the AI relationship graph service): this is the
plain managerial reporting-line chart every SMB expects.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import Employee
from app.services.org_chart_service import (
    attrition_rate,
    build_tree,
    headcount_by_department,
)

router = APIRouter(prefix="/org-chart", tags=["org-chart"])

_REPORT_ROLES = ("owner", "admin", "hr", "manager")

_ACTIVE_STATUSES = ("active", "activated", "invited", "pending_onboarding", "on_leave")


async def _org_rows(db: AsyncSession, org_id: UUID, include_terminated: bool = False) -> list[dict]:
    res = await db.execute(select(Employee).where(Employee.org_id == org_id))
    rows = []
    for e in res.scalars().all():
        if not include_terminated and e.status in ("terminated", "offboarded"):
            continue
        rows.append({
            "id": str(e.id),
            "manager_id": str(e.manager_employee_id) if e.manager_employee_id else None,
            "name": e.preferred_name or e.legal_name,
            "job_title": e.job_title,
            "department": e.department,
            "status": e.status,
        })
    return rows


@router.get("/tree")
async def tree(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    rows = await _org_rows(db, UUID(actor.org_id))
    return {"roots": build_tree(rows), "total": len(rows)}


@router.get("/headcount")
async def headcount(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in _REPORT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    rows = await _org_rows(db, UUID(actor.org_id))
    return {
        "by_department": headcount_by_department(rows),
        "total": len(rows),
    }


@router.get("/attrition")
async def attrition(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Trailing-12-month attrition: terminations / average headcount.

    Uses employees.termination_date (set by /employees/{id}/terminate) when
    the column exists; falls back to counting status='terminated' rows as
    all-time terminations otherwise.
    """
    if actor.role not in _REPORT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    org_id = UUID(actor.org_id)
    today = date.today()
    year_ago = today - timedelta(days=365)

    terminations_12mo: int
    window = "trailing_12_months"
    try:
        terminations_12mo = (await db.execute(text(
            "SELECT count(*) FROM public.employees "
            "WHERE org_id = :org AND status = 'terminated' "
            "AND termination_date IS NOT NULL AND termination_date >= :cutoff"
        ), {"org": str(org_id), "cutoff": year_ago})).scalar() or 0
    except Exception:
        await db.rollback()
        terminations_12mo = (await db.execute(text(
            "SELECT count(*) FROM public.employees "
            "WHERE org_id = :org AND status = 'terminated'"
        ), {"org": str(org_id)})).scalar() or 0
        window = "all_time (termination_date column unavailable)"

    current = (await db.execute(text(
        "SELECT count(*) FROM public.employees "
        "WHERE org_id = :org AND status NOT IN ('terminated','offboarded')"
    ), {"org": str(org_id)})).scalar() or 0
    # headcount a year ago ≈ current actives + those terminated during window
    start_headcount = current + terminations_12mo

    rate = attrition_rate(terminations_12mo, start_headcount, current)
    return {
        "window": window,
        "terminations": int(terminations_12mo),
        "headcount_start": int(start_headcount),
        "headcount_end": int(current),
        "attrition_rate": rate,
        "attrition_pct": round(rate * 100, 2),
    }
