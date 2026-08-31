"""Time-off engine: policies, accruals, balances, team calendar.

Extends the existing /pto request->approve flow (routers/pto.py) with the
BambooHR-style pieces SMBs actually buy for:

- POST /timeoff/policies            create accrual policy (hr)
- GET  /timeoff/policies            list policies
- POST /timeoff/policies/{id}/assign  assign an employee to a policy (hr)
- POST /timeoff/accruals/run        idempotently grant accruals up to today (hr)
- GET  /timeoff/balances            all balances (hr/manager)
- GET  /timeoff/balances/me         caller's balance (any employee)
- POST /timeoff/adjustments         manual +/- hours with note (hr)
- GET  /timeoff/calendar?start&end  approved/pending PTO in range (team calendar)

Balances are ledger-derived (signed sum), never a mutable counter, so every
hour is auditable. Approved PTO requests write usage entries from
routers/pto.py (fail-soft when no policy is assigned).

NOTE(payroll-bridge): pushing PTO balances into packages/payroll needs a
receiving endpoint on the payroll service (out of scope for this change —
see InternalPayrollConnector). TODO(payroll-sync): add
connector.push_timeoff_balances(...) once payroll exposes
/internal/timeoff-balances; the balance payload shape is already stable
(employee_id, policy name, balance_hours, as_of).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import (
    AuditEvent,
    Employee,
    PTORequest,
    TimeOffLedgerEntry,
    TimeOffPolicy,
    TimeOffPolicyAssignment,
)
from app.services.timeoff_service import (
    VALID_PERIODS,
    accrual_grants,
    cap_new_accrual,
    compute_balance,
)

router = APIRouter(prefix="/timeoff", tags=["timeoff"])

_HR_ROLES = ("owner", "admin", "hr")
_REVIEWER_ROLES = ("owner", "admin", "hr", "manager")


def _require(actor: Actor, roles: tuple[str, ...]) -> None:
    if actor.role not in roles:
        raise HTTPException(status_code=403, detail="Not allowed")


async def _my_employee(db: AsyncSession, actor: Actor) -> Employee | None:
    res = await db.execute(select(Employee).where(
        Employee.org_id == UUID(actor.org_id),
        Employee.user_id == UUID(actor.user_id),
    ))
    return res.scalar_one_or_none()


# =========================================================
# POLICIES
# =========================================================
class PolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    accrual_hours_per_period: float = Field(gt=0, le=999)
    accrual_period: str = "monthly"
    max_balance_hours: float | None = Field(default=None, gt=0)
    carryover_max_hours: float | None = Field(default=None, ge=0)
    hours_per_day: float = Field(default=8, gt=0, le=24)
    is_default: bool = False


@router.get("/policies")
async def list_policies(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    res = await db.execute(select(TimeOffPolicy).where(
        TimeOffPolicy.org_id == UUID(actor.org_id)).order_by(TimeOffPolicy.created_at.asc()))
    return [
        {
            "id": str(p.id), "name": p.name,
            "accrual_hours_per_period": float(p.accrual_hours_per_period),
            "accrual_period": p.accrual_period,
            "max_balance_hours": float(p.max_balance_hours) if p.max_balance_hours is not None else None,
            "carryover_max_hours": float(p.carryover_max_hours) if p.carryover_max_hours is not None else None,
            "hours_per_day": float(p.hours_per_day),
            "is_default": p.is_default,
        }
        for p in res.scalars().all()
    ]


@router.post("/policies")
async def create_policy(payload: PolicyCreate, actor: Actor = Depends(require_org),
                        db: AsyncSession = Depends(db_session)):
    _require(actor, _HR_ROLES)
    if payload.accrual_period not in VALID_PERIODS:
        raise HTTPException(status_code=422, detail=f"accrual_period must be one of {VALID_PERIODS}")
    org_id = UUID(actor.org_id)
    pol = TimeOffPolicy(org_id=org_id, **payload.model_dump())
    db.add(pol)
    await db.flush()
    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="timeoff.policy_created", entity_type="time_off_policy", entity_id=pol.id,
        payload=payload.model_dump(),
    ))
    await db.commit()
    return {"id": str(pol.id)}


class AssignBody(BaseModel):
    employee_id: UUID
    effective_date: date | None = None


@router.post("/policies/{policy_id}/assign")
async def assign_policy(policy_id: UUID, payload: AssignBody,
                        actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    _require(actor, _HR_ROLES)
    org_id = UUID(actor.org_id)

    pol = (await db.execute(select(TimeOffPolicy).where(
        TimeOffPolicy.id == policy_id, TimeOffPolicy.org_id == org_id))).scalar_one_or_none()
    if not pol:
        raise HTTPException(status_code=404, detail="Policy not found")
    emp = (await db.execute(select(Employee).where(
        Employee.id == payload.employee_id, Employee.org_id == org_id))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    eff = payload.effective_date or emp.start_date or date.today()
    existing = (await db.execute(select(TimeOffPolicyAssignment).where(
        TimeOffPolicyAssignment.org_id == org_id,
        TimeOffPolicyAssignment.employee_id == emp.id))).scalar_one_or_none()
    if existing:
        existing.policy_id = pol.id
        existing.effective_date = eff
    else:
        db.add(TimeOffPolicyAssignment(
            org_id=org_id, employee_id=emp.id, policy_id=pol.id, effective_date=eff))
    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="timeoff.policy_assigned", entity_type="employee", entity_id=emp.id,
        payload={"policy_id": str(pol.id), "effective_date": eff.isoformat()},
    ))
    await db.commit()
    return {"assigned": True, "policy_id": str(pol.id), "employee_id": str(emp.id),
            "effective_date": eff.isoformat()}


@router.get("/assignments")
async def list_assignments(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    _require(actor, _REVIEWER_ROLES)
    org_id = UUID(actor.org_id)
    res = await db.execute(select(TimeOffPolicyAssignment).where(
        TimeOffPolicyAssignment.org_id == org_id))
    return [
        {"employee_id": str(a.employee_id), "policy_id": str(a.policy_id),
         "effective_date": a.effective_date.isoformat()}
        for a in res.scalars().all()
    ]


# =========================================================
# ACCRUALS
# =========================================================
class AccrualRunBody(BaseModel):
    as_of: date | None = None


@router.post("/accruals/run")
async def run_accruals(payload: AccrualRunBody | None = None,
                       actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Grant every missing accrual up to `as_of` (default today). Idempotent:
    each accrual carries a period_key; existing keys are skipped, and grants
    are trimmed to the policy's max_balance cap."""
    _require(actor, _HR_ROLES)
    org_id = UUID(actor.org_id)
    as_of = (payload.as_of if payload else None) or date.today()

    assignments = (await db.execute(select(TimeOffPolicyAssignment).where(
        TimeOffPolicyAssignment.org_id == org_id))).scalars().all()
    policies = {p.id: p for p in (await db.execute(select(TimeOffPolicy).where(
        TimeOffPolicy.org_id == org_id))).scalars().all()}

    granted, skipped = 0, 0
    for a in assignments:
        pol = policies.get(a.policy_id)
        if not pol:
            continue
        entries = (await db.execute(select(TimeOffLedgerEntry).where(
            TimeOffLedgerEntry.org_id == org_id,
            TimeOffLedgerEntry.employee_id == a.employee_id))).scalars().all()
        existing_keys = {e.period_key for e in entries if e.period_key}
        balance = compute_balance([{"hours": float(e.hours)} for e in entries])

        for grant in accrual_grants(
                a.effective_date, as_of, pol.accrual_period,
                float(pol.accrual_hours_per_period)):
            if grant.period_key in existing_keys:
                skipped += 1
                continue
            cap = float(pol.max_balance_hours) if pol.max_balance_hours is not None else None
            hours = cap_new_accrual(balance, grant.hours, cap)
            db.add(TimeOffLedgerEntry(
                org_id=org_id, employee_id=a.employee_id, policy_id=pol.id,
                entry_type="accrual", hours=hours, effective_date=grant.effective_date,
                period_key=grant.period_key,
                note=None if hours == grant.hours else f"capped at {cap}",
                created_by_user_id=UUID(actor.user_id),
            ))
            balance += hours
            granted += 1

    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="timeoff.accruals_run", entity_type="time_off_ledger", entity_id=None,
        payload={"as_of": as_of.isoformat(), "granted": granted, "skipped": skipped},
    ))
    await db.commit()
    return {"as_of": as_of.isoformat(), "granted": granted, "skipped_existing": skipped}


# =========================================================
# BALANCES
# =========================================================
async def _balance_rows(db: AsyncSession, org_id: UUID, employee_id: UUID | None = None) -> list[dict]:
    q = select(TimeOffLedgerEntry).where(TimeOffLedgerEntry.org_id == org_id)
    if employee_id:
        q = q.where(TimeOffLedgerEntry.employee_id == employee_id)
    entries = (await db.execute(q)).scalars().all()
    policies = {p.id: p for p in (await db.execute(select(TimeOffPolicy).where(
        TimeOffPolicy.org_id == org_id))).scalars().all()}

    by_emp: dict[UUID, list[TimeOffLedgerEntry]] = {}
    for e in entries:
        by_emp.setdefault(e.employee_id, []).append(e)

    out = []
    for emp_id, rows in by_emp.items():
        accrued = sum(float(r.hours) for r in rows if r.entry_type == "accrual")
        used = -sum(float(r.hours) for r in rows if r.entry_type == "usage")
        pol = next((policies.get(r.policy_id) for r in rows if r.policy_id in policies), None)
        hours_per_day = float(pol.hours_per_day) if pol else 8.0
        balance = compute_balance([{"hours": float(r.hours)} for r in rows])
        out.append({
            "employee_id": str(emp_id),
            "policy": pol.name if pol else None,
            "accrued_hours": round(accrued, 2),
            "used_hours": round(used, 2),
            "balance_hours": balance,
            "balance_days": round(balance / hours_per_day, 2) if hours_per_day else None,
            "hours_per_day": hours_per_day,
        })
    return out


@router.get("/balances")
async def balances(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    _require(actor, _REVIEWER_ROLES)
    org_id = UUID(actor.org_id)
    rows = await _balance_rows(db, org_id)
    emps = {str(e.id): e for e in (await db.execute(select(Employee).where(
        Employee.org_id == org_id))).scalars().all()}
    for r in rows:
        emp = emps.get(r["employee_id"])
        r["employee_name"] = emp.legal_name if emp else None
    rows.sort(key=lambda r: (r["employee_name"] or ""))
    return rows


@router.get("/balances/me")
async def my_balance(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    me = await _my_employee(db, actor)
    if not me:
        return {"employee_id": None, "balance_hours": 0, "note": "No employee record linked."}
    rows = await _balance_rows(db, org_id, me.id)
    if not rows:
        return {"employee_id": str(me.id), "policy": None, "accrued_hours": 0,
                "used_hours": 0, "balance_hours": 0, "balance_days": 0,
                "note": "No time-off policy assigned yet — ask HR."}
    return rows[0]


class AdjustmentBody(BaseModel):
    employee_id: UUID
    hours: float = Field(ge=-999, le=999)
    note: str = Field(min_length=1, max_length=500)


@router.post("/adjustments")
async def add_adjustment(payload: AdjustmentBody, actor: Actor = Depends(require_org),
                         db: AsyncSession = Depends(db_session)):
    _require(actor, _HR_ROLES)
    if payload.hours == 0:
        raise HTTPException(status_code=422, detail="hours must be non-zero")
    org_id = UUID(actor.org_id)
    emp = (await db.execute(select(Employee).where(
        Employee.id == payload.employee_id, Employee.org_id == org_id))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    entry = TimeOffLedgerEntry(
        org_id=org_id, employee_id=emp.id, entry_type="adjustment",
        hours=payload.hours, effective_date=date.today(), note=payload.note.strip(),
        created_by_user_id=UUID(actor.user_id))
    db.add(entry)
    await db.flush()
    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="timeoff.adjustment", entity_type="time_off_ledger", entity_id=entry.id,
        payload={"employee_id": str(emp.id), "hours": payload.hours, "note": payload.note},
    ))
    await db.commit()
    return {"id": str(entry.id)}


# =========================================================
# TEAM CALENDAR
# =========================================================
@router.get("/calendar")
async def team_calendar(start: date, end: date,
                        actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """PTO requests overlapping [start, end]. Everyone in the org can see
    who's out (names + dates + status only — no reasons for non-reviewers)."""
    if end < start:
        raise HTTPException(status_code=422, detail="end before start")
    org_id = UUID(actor.org_id)
    reqs = (await db.execute(select(PTORequest).where(
        PTORequest.org_id == org_id,
        PTORequest.status.in_(("pending", "approved")),
        PTORequest.start_date <= end,
        PTORequest.end_date >= start,
    ).order_by(PTORequest.start_date.asc()))).scalars().all()
    emps = {e.id: e for e in (await db.execute(select(Employee).where(
        Employee.org_id == org_id))).scalars().all()}
    is_reviewer = actor.role in _REVIEWER_ROLES
    return [
        {
            "id": str(r.id),
            "employee_id": str(r.employee_id),
            "employee_name": (emps.get(r.employee_id).preferred_name
                              or emps.get(r.employee_id).legal_name) if r.employee_id in emps else None,
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "status": r.status,
            **({"reason": r.reason} if is_reviewer else {}),
        }
        for r in reqs
    ]
