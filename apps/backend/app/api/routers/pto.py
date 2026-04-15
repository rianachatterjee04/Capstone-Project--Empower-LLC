from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.api.schemas import PTORequestCreate, PTORequestOut, PTORequestReview
from app.db.models import AuditEvent, Employee, PTORequest

router = APIRouter(prefix="/pto", tags=["pto"])


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
