"""HR -> Payroll sync admin endpoints (the HR side of the payroll bridge).

HR is the source of truth for people; these endpoints PUSH employees and
timesheet hours into the standalone payroll service (packages/payroll,
PAYROLL_API_URL, default http://localhost:8050) through
InternalPayrollConnector.  Org-scoped via the normal auth deps; restricted
to owner/admin/hr roles.

Fail-soft: when payroll is unreachable (or its license is not activated)
the response is 200 with {synced: 0, error: ...} so HR screens degrade
gracefully instead of erroring.
"""
from __future__ import annotations

import os
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import Employee
from app.integrations.internal_payroll import (InternalPayrollConnector,
                                               load_current_comp,
                                               map_hr_employee)

router = APIRouter(prefix="/payroll-sync", tags=["payroll-sync"])

_ALLOWED_ROLES = ("owner", "admin", "hr")


def _require_hr_admin(actor: Actor) -> None:
    if actor.role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")


async def _org_employees(db: AsyncSession, org_id: str) -> list[Employee]:
    res = await db.execute(select(Employee).where(
        Employee.org_id == UUID(org_id)).order_by(Employee.created_at.asc()))
    return list(res.scalars().all())


@router.post("/employees")
async def sync_employees(actor: Actor = Depends(require_org),
                         db: AsyncSession = Depends(db_session)):
    """Push every HR employee of this org into payroll (bulk upsert,
    matched by hr_employee_id). Returns per-record results from payroll."""
    _require_hr_admin(actor)
    rows = await _org_employees(db, actor.org_id)
    # Enrich each employee with its CURRENT effective compensation so payroll
    # receives pay_basis/basis_amount (hire -> comp -> pay-run). Employees with
    # no comp row still sync as people; they just carry no comp until one is set.
    comp_by_emp = await load_current_comp(
        db, actor.org_id, [str(e.id) for e in rows])
    # Org's default payroll PaySchedule id (lives in the payroll service): set
    # PAYROLL_DEFAULT_SCHEDULE_ID so synced employees land on a schedule and are
    # picked up by runs. Absent it, they sync but are excluded from runs.
    default_schedule_id = os.getenv("PAYROLL_DEFAULT_SCHEDULE_ID")
    connector = InternalPayrollConnector()
    result = await connector.push_employees(
        actor.org_id,
        [map_hr_employee(e, comp=comp_by_emp.get(str(e.id)),
                         default_schedule_id=default_schedule_id) for e in rows])
    if not result.ok:
        return {"synced": 0, **result.details}
    return result.details


class TimesheetEntryIn(BaseModel):
    """One employee's hours for the period. Identify the employee by HR
    employee id or email (id wins)."""
    employee_id: str | None = None
    email: str | None = None
    # keys: regular | overtime | training | staff_meeting
    hours_by_type: dict[str, float]


class TimesheetSyncBody(BaseModel):
    entries: list[TimesheetEntryIn] = []
    # hr-api has no native time-tracking store yet: when `entries` is empty,
    # one entry per active employee is generated with this many regular hours.
    default_regular_hours: float = 80.0


@router.post("/timesheets")
async def sync_timesheets(start: date, end: date,
                          body: TimesheetSyncBody | None = None,
                          actor: Actor = Depends(require_org),
                          db: AsyncSession = Depends(db_session)):
    """Push timesheet hours for [start, end] into payroll as pending
    imports (payroll drafts hourly earning lines from them)."""
    _require_hr_admin(actor)
    if end < start:
        raise HTTPException(status_code=422, detail="end before start")
    body = body or TimesheetSyncBody()
    rows = await _org_employees(db, actor.org_id)
    by_id = {str(e.id): e for e in rows}
    by_email = {e.email: e for e in rows}

    entries, unmatched = [], []
    if body.entries:
        for item in body.entries:
            emp = (by_id.get(item.employee_id or "")
                   or by_email.get(item.email or ""))
            if emp is None:
                unmatched.append({"employee_id": item.employee_id,
                                  "email": item.email,
                                  "reason": "no HR employee match"})
                continue
            entries.append({"hr_employee_id": str(emp.id),
                            "hours_by_type": item.hours_by_type})
    else:
        entries = [{"hr_employee_id": str(e.id),
                    "hours_by_type": {"regular": body.default_regular_hours}}
                   for e in rows if e.status not in ("terminated", "offboarded")]

    connector = InternalPayrollConnector()
    result = await connector.push_timesheets(
        actor.org_id, start.isoformat(), end.isoformat(), entries)
    if not result.ok:
        return {"synced": 0, "unmatched": unmatched, **result.details}
    return {**result.details, "unmatched": unmatched}
