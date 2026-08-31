from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.api.schemas import PTORequestCreate, PTORequestOut, PTORequestReview
from app.db.models import (
    AuditEvent,
    Employee,
    PTORequest,
    TimeOffLedgerEntry,
    TimeOffPolicy,
    TimeOffPolicyAssignment,
)
from app.services.approvals_adapter import emit_approval_request
from app.services.timeoff_service import usage_hours

router = APIRouter(prefix="/pto", tags=["pto"])


async def _record_usage_fail_soft(
    db: AsyncSession, org_id: UUID, req: PTORequest, actor: Actor
) -> None:
    """Write a usage entry to the time-off ledger for an approved request.

    Fail-soft: if the employee has no policy assignment (orgs that haven't
    adopted the accrual engine yet) this is a silent no-op — approval flow
    behavior is unchanged. Idempotent per request via the partial unique
    index uq_tol_usage_request.
    """
    try:
        assignment = (await db.execute(
            select(TimeOffPolicyAssignment).where(
                TimeOffPolicyAssignment.org_id == org_id,
                TimeOffPolicyAssignment.employee_id == req.employee_id,
            )
        )).scalar_one_or_none()
        if not assignment:
            return
        policy = (await db.execute(
            select(TimeOffPolicy).where(TimeOffPolicy.id == assignment.policy_id)
        )).scalar_one_or_none()
        if not policy:
            return
        existing = (await db.execute(
            select(TimeOffLedgerEntry).where(
                TimeOffLedgerEntry.pto_request_id == req.id,
                TimeOffLedgerEntry.entry_type == "usage",
            )
        )).scalar_one_or_none()
        if existing:
            return
        hours = usage_hours(req.start_date, req.end_date, float(policy.hours_per_day))
        if hours <= 0:
            return
        db.add(TimeOffLedgerEntry(
            org_id=org_id,
            employee_id=req.employee_id,
            policy_id=policy.id,
            entry_type="usage",
            hours=-hours,
            effective_date=req.start_date,
            pto_request_id=req.id,
            note=f"PTO {req.start_date.isoformat()} → {req.end_date.isoformat()}",
            created_by_user_id=UUID(actor.user_id),
        ))
    except Exception:
        # Never block an approval on ledger bookkeeping.
        pass


def _is_reviewer_role(role: str) -> bool:
    return role in ("owner", "admin", "hr", "manager")


@router.get("/requests", response_model=list[PTORequestOut])
async def list_pto_requests(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = UUID(actor.org_id)
    if _is_reviewer_role(actor.role):
        q = (
            select(PTORequest)
            .where(PTORequest.org_id == org_id)
            .order_by(PTORequest.created_at.desc())
        )
    else:
        er = await db.execute(
            select(Employee).where(
                Employee.org_id == org_id,
                Employee.user_id == UUID(actor.user_id),
            )
        )
        me = er.scalar_one_or_none()
        if not me:
            return []
        q = (
            select(PTORequest)
            .where(PTORequest.org_id == org_id, PTORequest.employee_id == me.id)
            .order_by(PTORequest.created_at.desc())
        )

    res = await db.execute(q)
    return res.scalars().all()


@router.post("/requests", response_model=PTORequestOut)
async def create_pto_request(
    payload: PTORequestCreate,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = UUID(actor.org_id)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    er = await db.execute(
        select(Employee).where(
            Employee.org_id == org_id,
            Employee.user_id == UUID(actor.user_id),
        )
    )
    me = er.scalar_one_or_none()
    if not me:
        raise HTTPException(
            status_code=400,
            detail="Could not find your employee record in this org.",
        )

    req = PTORequest(
        org_id=org_id,
        employee_id=me.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason.strip(),
        status="pending",
    )
    db.add(req)
    await db.flush()
    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="pto.requested",
            entity_type="pto_request",
            entity_id=req.id,
            payload={
                "start_date": payload.start_date.isoformat(),
                "end_date": payload.end_date.isoformat(),
            },
        )
    )
    await db.commit()
    await db.refresh(req)

    # TODO(platform-approvals): today this is a no-op stub; once the platform
    # approvals inbox exists, this call will surface the request there too.
    emit_approval_request(
        org_id=str(org_id),
        kind="timeoff.request",
        entity_id=str(req.id),
        requested_by_user_id=actor.user_id,
        summary=f"PTO {req.start_date.isoformat()} → {req.end_date.isoformat()}",
        payload={"employee_id": str(me.id)},
    )
    return req


@router.post("/requests/{request_id}/approve", response_model=PTORequestOut)
async def approve_pto_request(
    request_id: UUID,
    payload: PTORequestReview,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _is_reviewer_role(actor.role):
        raise HTTPException(status_code=403, detail="Not allowed")
    org_id = UUID(actor.org_id)
    req = (
        await db.execute(
            select(PTORequest).where(PTORequest.id == request_id, PTORequest.org_id == org_id)
        )
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="PTO request not found")

    req.status = "approved"
    req.reviewed_by_user_id = UUID(actor.user_id)
    req.reviewed_at = datetime.now(timezone.utc)
    req.review_note = (payload.review_note or "").strip() or None
    db.add(req)
    # Deduct hours from the accrual ledger (no-op for orgs without policies).
    await _record_usage_fail_soft(db, org_id, req, actor)
    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="pto.approved",
            entity_type="pto_request",
            entity_id=req.id,
            payload={"review_note": req.review_note},
        )
    )
    await db.commit()
    await db.refresh(req)
    return req


@router.post("/requests/{request_id}/deny", response_model=PTORequestOut)
async def deny_pto_request(
    request_id: UUID,
    payload: PTORequestReview,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _is_reviewer_role(actor.role):
        raise HTTPException(status_code=403, detail="Not allowed")
    org_id = UUID(actor.org_id)
    req = (
        await db.execute(
            select(PTORequest).where(PTORequest.id == request_id, PTORequest.org_id == org_id)
        )
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="PTO request not found")

    req.status = "denied"
    req.reviewed_by_user_id = UUID(actor.user_id)
    req.reviewed_at = datetime.now(timezone.utc)
    req.review_note = (payload.review_note or "").strip() or None
    db.add(req)
    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="pto.denied",
            entity_type="pto_request",
            entity_id=req.id,
            payload={"review_note": req.review_note},
        )
    )
    await db.commit()
    await db.refresh(req)
    return req
