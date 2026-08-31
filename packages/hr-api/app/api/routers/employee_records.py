"""Effective-dated employee records (PeopleSoft pattern) + self-service.

- Comp history:   GET/POST /employee-records/{employee_id}/comp-history
                  GET      /employee-records/{employee_id}/comp-current
- Job history:    GET      /employee-records/{employee_id}/job-history
                  POST     /employee-records/{employee_id}/job-change
- Emergency:      GET/POST /employee-records/{employee_id}/emergency-contacts
                  DELETE   /employee-records/emergency-contacts/{contact_id}
- Self-service:   GET      /employee-records/me
                  PATCH    /employee-records/me/profile   (audited)

Effective dating rules live in app/services/effective_dating.py: exactly one
open record (end_date NULL) per employee per history; inserting a new record
closes the previous one the day before the new effective date.

Comp history is the seam performance reviews feed into: pass `review_id`
(performance_reviews.id) + reason="review" when a comp change comes out of a
review cycle, so every raise is traceable to the decision that caused it.
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
    CompHistory,
    EmergencyContact,
    Employee,
    JobHistory,
)
from app.services.effective_dating import (
    closing_end_date,
    resolve_as_of,
    validate_new_record,
)

router = APIRouter(prefix="/employee-records", tags=["employee-records"])

_HR_ROLES = ("owner", "admin", "hr")


async def _my_employee(db: AsyncSession, actor: Actor) -> Employee | None:
    res = await db.execute(select(Employee).where(
        Employee.org_id == UUID(actor.org_id),
        Employee.user_id == UUID(actor.user_id)))
    return res.scalar_one_or_none()


async def _employee_or_404(db: AsyncSession, actor: Actor, employee_id: UUID) -> Employee:
    emp = (await db.execute(select(Employee).where(
        Employee.id == employee_id,
        Employee.org_id == UUID(actor.org_id)))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


async def _require_hr_or_self(db: AsyncSession, actor: Actor, employee_id: UUID) -> Employee:
    """HR roles may access anyone in the org; anyone else only themselves."""
    emp = await _employee_or_404(db, actor, employee_id)
    if actor.role in _HR_ROLES:
        return emp
    me = await _my_employee(db, actor)
    if not me or me.id != emp.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    return emp


# =========================================================
# COMP HISTORY (effective-dated; sensitive → HR or self, read-only for self)
# =========================================================
def _comp_dict(r: CompHistory) -> dict:
    return {
        "id": str(r.id), "amount": float(r.amount), "currency": r.currency,
        "basis": r.basis, "effective_date": r.effective_date.isoformat(),
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "reason": r.reason, "review_id": str(r.review_id) if r.review_id else None,
    }


@router.get("/{employee_id}/comp-history")
async def comp_history(employee_id: UUID, actor: Actor = Depends(require_org),
                       db: AsyncSession = Depends(db_session)):
    await _require_hr_or_self(db, actor, employee_id)
    rows = (await db.execute(select(CompHistory).where(
        CompHistory.employee_id == employee_id,
        CompHistory.org_id == UUID(actor.org_id),
    ).order_by(CompHistory.effective_date.desc()))).scalars().all()
    return [_comp_dict(r) for r in rows]


class CompCreate(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "USD"
    basis: str = "salary"           # salary (annual) | hourly
    effective_date: date
    reason: str | None = None       # hire | merit | promotion | market | review
    review_id: UUID | None = None   # link back to performance_reviews.id


@router.post("/{employee_id}/comp-history")
async def add_comp(employee_id: UUID, payload: CompCreate,
                   actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in _HR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if payload.basis not in ("salary", "hourly"):
        raise HTTPException(status_code=422, detail="basis must be salary or hourly")
    emp = await _employee_or_404(db, actor, employee_id)
    org_id = UUID(actor.org_id)

    rows = (await db.execute(select(CompHistory).where(
        CompHistory.employee_id == emp.id, CompHistory.org_id == org_id))).scalars().all()
    try:
        validate_new_record(
            [{"effective_date": r.effective_date, "end_date": r.end_date} for r in rows],
            payload.effective_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # close the open record (PeopleSoft-style)
    for r in rows:
        if r.end_date is None:
            r.end_date = closing_end_date(payload.effective_date)

    rec = CompHistory(
        org_id=org_id, employee_id=emp.id, amount=payload.amount,
        currency=payload.currency, basis=payload.basis,
        effective_date=payload.effective_date, reason=payload.reason,
        review_id=payload.review_id, created_by_user_id=UUID(actor.user_id))
    db.add(rec)
    await db.flush()
    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="employee.comp_changed", entity_type="employee", entity_id=emp.id,
        payload={"amount": payload.amount, "basis": payload.basis,
                 "effective_date": payload.effective_date.isoformat(),
                 "reason": payload.reason,
                 "review_id": str(payload.review_id) if payload.review_id else None},
    ))
    await db.commit()
    return _comp_dict(rec)


@router.get("/{employee_id}/comp-current")
async def comp_current(employee_id: UUID, actor: Actor = Depends(require_org),
                       db: AsyncSession = Depends(db_session)):
    await _require_hr_or_self(db, actor, employee_id)
    rows = (await db.execute(select(CompHistory).where(
        CompHistory.employee_id == employee_id,
        CompHistory.org_id == UUID(actor.org_id)))).scalars().all()
    current = resolve_as_of(
        [{"effective_date": r.effective_date, "end_date": r.end_date, "_row": r} for r in rows],
        date.today())
    return _comp_dict(current["_row"]) if current else None


# =========================================================
# JOB HISTORY (title / department / manager, effective-dated)
# =========================================================
def _job_dict(r: JobHistory) -> dict:
    return {
        "id": str(r.id), "job_title": r.job_title, "department": r.department,
        "manager_employee_id": str(r.manager_employee_id) if r.manager_employee_id else None,
        "effective_date": r.effective_date.isoformat(),
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "reason": r.reason,
    }


@router.get("/{employee_id}/job-history")
async def job_history(employee_id: UUID, actor: Actor = Depends(require_org),
                      db: AsyncSession = Depends(db_session)):
    await _require_hr_or_self(db, actor, employee_id)
    rows = (await db.execute(select(JobHistory).where(
        JobHistory.employee_id == employee_id,
        JobHistory.org_id == UUID(actor.org_id),
    ).order_by(JobHistory.effective_date.desc()))).scalars().all()
    return [_job_dict(r) for r in rows]


class JobChange(BaseModel):
    job_title: str | None = None
    department: str | None = None
    manager_employee_id: UUID | None = None
    effective_date: date
    reason: str | None = None       # hire | promotion | transfer | reorg


@router.post("/{employee_id}/job-change")
async def job_change(employee_id: UUID, payload: JobChange,
                     actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Record an effective-dated job change AND apply it to the live
    employees row (title/department/manager) in one transaction."""
    if actor.role not in _HR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if payload.job_title is None and payload.department is None and payload.manager_employee_id is None:
        raise HTTPException(status_code=422, detail="Nothing to change")
    emp = await _employee_or_404(db, actor, employee_id)
    org_id = UUID(actor.org_id)

    if payload.manager_employee_id:
        if payload.manager_employee_id == emp.id:
            raise HTTPException(status_code=422, detail="Employee cannot manage themselves")
        await _employee_or_404(db, actor, payload.manager_employee_id)

    rows = (await db.execute(select(JobHistory).where(
        JobHistory.employee_id == emp.id, JobHistory.org_id == org_id))).scalars().all()
    try:
        validate_new_record(
            [{"effective_date": r.effective_date, "end_date": r.end_date} for r in rows],
            payload.effective_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    for r in rows:
        if r.end_date is None:
            r.end_date = closing_end_date(payload.effective_date)

    # new record inherits unchanged fields from the live row
    new_title = payload.job_title if payload.job_title is not None else emp.job_title
    new_dept = payload.department if payload.department is not None else emp.department
    new_mgr = payload.manager_employee_id if payload.manager_employee_id is not None else emp.manager_employee_id

    rec = JobHistory(
        org_id=org_id, employee_id=emp.id, job_title=new_title, department=new_dept,
        manager_employee_id=new_mgr, effective_date=payload.effective_date,
        reason=payload.reason, created_by_user_id=UUID(actor.user_id))
    db.add(rec)

    # apply to live row
    emp.job_title = new_title
    emp.department = new_dept
    emp.manager_employee_id = new_mgr

    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="employee.job_changed", entity_type="employee", entity_id=emp.id,
        payload={"job_title": new_title, "department": new_dept,
                 "manager_employee_id": str(new_mgr) if new_mgr else None,
                 "effective_date": payload.effective_date.isoformat(),
                 "reason": payload.reason},
    ))
    await db.commit()
    return _job_dict(rec)


# =========================================================
# EMERGENCY CONTACTS (HR or the employee themselves)
# =========================================================
def _contact_dict(c: EmergencyContact) -> dict:
    return {
        "id": str(c.id), "employee_id": str(c.employee_id), "full_name": c.full_name,
        "relationship": c.relationship, "phone": c.phone, "email": c.email,
        "is_primary": c.is_primary,
    }


@router.get("/{employee_id}/emergency-contacts")
async def list_contacts(employee_id: UUID, actor: Actor = Depends(require_org),
                        db: AsyncSession = Depends(db_session)):
    await _require_hr_or_self(db, actor, employee_id)
    rows = (await db.execute(select(EmergencyContact).where(
        EmergencyContact.employee_id == employee_id,
        EmergencyContact.org_id == UUID(actor.org_id),
    ).order_by(EmergencyContact.is_primary.desc(), EmergencyContact.created_at.asc()))).scalars().all()
    return [_contact_dict(c) for c in rows]


class ContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    relationship: str | None = None
    phone: str = Field(min_length=3, max_length=40)
    email: str | None = None
    is_primary: bool = False


@router.post("/{employee_id}/emergency-contacts")
async def add_contact(employee_id: UUID, payload: ContactCreate,
                      actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    emp = await _require_hr_or_self(db, actor, employee_id)
    org_id = UUID(actor.org_id)
    if payload.is_primary:
        others = (await db.execute(select(EmergencyContact).where(
            EmergencyContact.employee_id == emp.id,
            EmergencyContact.org_id == org_id))).scalars().all()
        for o in others:
            o.is_primary = False
    c = EmergencyContact(org_id=org_id, employee_id=emp.id, **payload.model_dump())
    db.add(c)
    await db.flush()
    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="employee.emergency_contact_added", entity_type="employee", entity_id=emp.id,
        payload={"contact_id": str(c.id), "full_name": payload.full_name},
    ))
    await db.commit()
    return _contact_dict(c)


@router.delete("/emergency-contacts/{contact_id}")
async def delete_contact(contact_id: UUID, actor: Actor = Depends(require_org),
                         db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    c = (await db.execute(select(EmergencyContact).where(
        EmergencyContact.id == contact_id,
        EmergencyContact.org_id == org_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    await _require_hr_or_self(db, actor, c.employee_id)
    await db.delete(c)
    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="employee.emergency_contact_removed", entity_type="employee",
        entity_id=c.employee_id, payload={"contact_id": str(contact_id)},
    ))
    await db.commit()
    return {"deleted": True}


# =========================================================
# SELF-SERVICE: my record + audited profile edits
# =========================================================
@router.get("/me")
async def my_record(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    me = await _my_employee(db, actor)
    if not me:
        raise HTTPException(status_code=404, detail="No employee record linked to your account")
    return {
        "id": str(me.id), "legal_name": me.legal_name, "preferred_name": me.preferred_name,
        "email": me.email, "job_title": me.job_title, "department": me.department,
        "location": me.location, "status": me.status,
        "start_date": me.start_date.isoformat() if me.start_date else None,
        "manager_employee_id": str(me.manager_employee_id) if me.manager_employee_id else None,
    }


class ProfilePatch(BaseModel):
    preferred_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)


@router.patch("/me/profile")
async def patch_my_profile(payload: ProfilePatch, actor: Actor = Depends(require_org),
                           db: AsyncSession = Depends(db_session)):
    """Employee self-service edits, limited to non-authoritative fields
    (preferred name, location). Every change is written to AuditEvent with
    before/after values."""
    me = await _my_employee(db, actor)
    if not me:
        raise HTTPException(status_code=404, detail="No employee record linked to your account")

    changes: dict[str, dict] = {}
    if payload.preferred_name is not None and payload.preferred_name.strip() != (me.preferred_name or ""):
        changes["preferred_name"] = {"from": me.preferred_name, "to": payload.preferred_name.strip() or None}
        me.preferred_name = payload.preferred_name.strip() or None
    if payload.location is not None and payload.location.strip() != (me.location or ""):
        changes["location"] = {"from": me.location, "to": payload.location.strip() or None}
        me.location = payload.location.strip() or None

    if not changes:
        return {"updated": False}

    db.add(AuditEvent(
        org_id=UUID(actor.org_id), actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="employee.profile_self_edited", entity_type="employee", entity_id=me.id,
        payload=changes,
    ))
    await db.commit()
    return {"updated": True, "changes": changes}
