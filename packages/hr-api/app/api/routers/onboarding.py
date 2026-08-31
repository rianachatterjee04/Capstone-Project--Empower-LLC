from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, or_, update
from app.core.json_utils import json_safe
from uuid import UUID
from datetime import datetime, timedelta, timezone

from app.api.deps import require_org, db_session, Actor
from app.api.schemas import (
    OnboardingPacketOut,
    OnboardingPacketCreate,
    OnboardingPacketPatch,
    OnboardingPacketRequestCreate,
    OnboardingPacketRequestOut,
)
from app.db.models import OnboardingPacket, Employee, AuditEvent, OnboardingPacketRequest

# 🧠 Behavioral OS
from app.workflow.engine import engine

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def _resolve_packet_requests_for_employee(db: AsyncSession, org_id: UUID, employee: Employee) -> None:
    conds = [OnboardingPacketRequest.employee_id == employee.id]
    if employee.user_id is not None:
        conds.append(OnboardingPacketRequest.requested_by_user_id == employee.user_id)
    await db.execute(
        update(OnboardingPacketRequest)
        .where(
            OnboardingPacketRequest.org_id == org_id,
            OnboardingPacketRequest.status == "pending",
            or_(*conds),
        )
        .values(status="done", resolved_at=datetime.now(timezone.utc))
    )


# ---------------------------------------------------------
# LIST PACKETS
# ---------------------------------------------------------
@router.get("/packets", response_model=list[OnboardingPacketOut])
async def list_packets(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    
    # HR/admin/owner see all packets
    if actor.role in ("owner", "admin", "hr"):
        q = select(OnboardingPacket).where(
            OnboardingPacket.org_id == org_id
        ).order_by(OnboardingPacket.created_at.desc())
    else:
        # Employees only see their own packet
        er = await db.execute(
            select(Employee).where(
                Employee.org_id == org_id,
                Employee.user_id == UUID(actor.user_id)
            )
        )
        me = er.scalar_one_or_none()
        if not me:
            return []  # No employee record linked to this user yet
        q = select(OnboardingPacket).where(
            OnboardingPacket.org_id == org_id,
            OnboardingPacket.employee_id == me.id
        ).order_by(OnboardingPacket.created_at.desc())
    
    res = await db.execute(q)
    return res.scalars().all()


# ---------------------------------------------------------
# PACKET REQUESTS (employee → HR)
# ---------------------------------------------------------
@router.get("/packet-requests/me", response_model=OnboardingPacketRequestOut | None)
async def my_packet_request(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    uid = UUID(actor.user_id)
    res = await db.execute(
        select(OnboardingPacketRequest)
        .where(
            OnboardingPacketRequest.org_id == org_id,
            OnboardingPacketRequest.requested_by_user_id == uid,
            OnboardingPacketRequest.status == "pending",
        )
        .order_by(OnboardingPacketRequest.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


@router.post("/packet-requests", response_model=OnboardingPacketRequestOut)
async def create_packet_request(
    payload: OnboardingPacketRequestCreate,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = UUID(actor.org_id)
    uid = UUID(actor.user_id)

    er = await db.execute(select(Employee).where(Employee.org_id == org_id, Employee.user_id == uid))
    me = er.scalar_one_or_none()
    if me:
        existing_pkt = (
            await db.execute(
                select(OnboardingPacket).where(
                    OnboardingPacket.org_id == org_id,
                    OnboardingPacket.employee_id == me.id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing_pkt:
            raise HTTPException(status_code=400, detail="You already have an onboarding packet.")

    existing_req = (
        await db.execute(
            select(OnboardingPacketRequest).where(
                OnboardingPacketRequest.org_id == org_id,
                OnboardingPacketRequest.requested_by_user_id == uid,
                OnboardingPacketRequest.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing_req:
        return existing_req

    email = actor.claims.get("email") or None
    msg = (payload.message or "").strip() or None
    req = OnboardingPacketRequest(
        org_id=org_id,
        requested_by_user_id=uid,
        employee_id=me.id if me else None,
        requester_email=email,
        message=msg,
        status="pending",
    )
    db.add(req)
    await db.flush()
    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=uid,
            actor_role=actor.role,
            event_type="onboarding.packet_requested",
            entity_type="onboarding_packet_request",
            entity_id=req.id,
            payload=json_safe({"message": msg}),
        )
    )
    await db.commit()
    await db.refresh(req)
    return req


@router.get("/packet-requests", response_model=list[OnboardingPacketRequestOut])
async def list_packet_requests(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    org_id = UUID(actor.org_id)
    res = await db.execute(
        select(OnboardingPacketRequest)
        .where(OnboardingPacketRequest.org_id == org_id, OnboardingPacketRequest.status == "pending")
        .order_by(OnboardingPacketRequest.created_at.desc())
    )
    return res.scalars().all()


# ---------------------------------------------------------
# CREATE PACKET (Offer accepted)
# ---------------------------------------------------------
@router.post("/packets", response_model=OnboardingPacketOut)
async def create_packet(payload: OnboardingPacketCreate, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    er = await db.execute(select(Employee).where(Employee.id == payload.employee_id, Employee.org_id == org_id))
    employee = er.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    pkt = OnboardingPacket(
        org_id=org_id,
        employee_id=payload.employee_id,
        requested_items=payload.requested_items,
        submitted_items={},
        status="pending",
        # due_at=datetime.utcnow() + timedelta(days=3)
    )

    db.add(pkt)
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="onboarding.created",
        entity_type="onboarding_packet",
        entity_id=pkt.id,
        payload=json_safe(payload.model_dump())
    ))

    await _resolve_packet_requests_for_employee(db, org_id, employee)

    await db.commit()
    await db.refresh(pkt)

    # 🧠 Brain: onboarding started
    engine.trigger(
        "employee.onboarding.started",
        {
            "org_id": actor.org_id,
            "employee_id": str(pkt.employee_id)
        }
    )

    return pkt


# ---------------------------------------------------------
# UPDATE PACKET (Employee submits forms)
# ---------------------------------------------------------
@router.patch("/packets/{packet_id}", response_model=OnboardingPacketOut)
async def patch_packet(packet_id: UUID, payload: OnboardingPacketPatch, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    org_id = UUID(actor.org_id)

    res = await db.execute(select(OnboardingPacket).where(OnboardingPacket.id == packet_id, OnboardingPacket.org_id == org_id))
    pkt = res.scalar_one_or_none()
    if not pkt:
        raise HTTPException(status_code=404, detail="Packet not found")

    is_hr = actor.role in ("owner", "admin", "hr")

    if not is_hr:
        er = await db.execute(select(Employee).where(Employee.org_id == org_id, Employee.user_id == UUID(actor.user_id)))
        me = er.scalar_one_or_none()
        if not me or me.id != pkt.employee_id:
            raise HTTPException(status_code=403, detail="Not allowed")

    # merge submitted forms
    if payload.submitted_items is not None:
        pkt.submitted_items = {**(pkt.submitted_items or {}), **payload.submitted_items}
        pkt.status = "in_progress"

    if payload.status is not None:
        # Non-HR (employee self-service) may only move the packet along the
        # self-serve path — they must never mark it verified/activated, which
        # would let an activate call succeed with no HR review of documents.
        if not is_hr and payload.status not in ("in_progress", "submitted"):
            raise HTTPException(status_code=403, detail="Not allowed to set this status")
        pkt.status = payload.status

    # auto-complete detection
    if pkt.requested_items and set(pkt.requested_items).issubset(set((pkt.submitted_items or {}).keys())):
        pkt.status = "completed"

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="onboarding.updated",
        entity_type="onboarding_packet",
        entity_id=pkt.id,
        payload=payload.model_dump(exclude_none=True)
    ))

    await db.commit()
    await db.refresh(pkt)

    # 🧠 Brain trigger
    engine.trigger(
        "employee.onboarding.updated",
        {
            "org_id": actor.org_id,
            "employee_id": str(pkt.employee_id),
            "status": pkt.status
        }
    )

    return pkt


# ---------------------------------------------------------
# VERIFY (I-9 Section 2)
# ---------------------------------------------------------
@router.post("/packets/{packet_id}/verify")
async def verify_packet(packet_id: UUID, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    res = await db.execute(select(OnboardingPacket).where(OnboardingPacket.id == packet_id, OnboardingPacket.org_id == org_id))
    pkt = res.scalar_one_or_none()
    if not pkt:
        raise HTTPException(status_code=404, detail="Packet not found")

    if pkt.status != "completed":
        raise HTTPException(status_code=400, detail="Cannot verify incomplete onboarding")

    pkt.status = "verified"

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="onboarding.verified",
        entity_type="onboarding_packet",
        entity_id=pkt.id,
        payload={}
    ))

    await db.commit()

    engine.trigger(
        "employee.onboarding.verified",
        {
            "org_id": actor.org_id,
            "employee_id": str(pkt.employee_id)
        }
    )

    return {"status": "verified"}


# ---------------------------------------------------------
# ACTIVATE EMPLOYEE
# ---------------------------------------------------------
@router.post("/packets/{packet_id}/activate")
async def activate_employee(packet_id: UUID, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    res = await db.execute(select(OnboardingPacket).where(OnboardingPacket.id == packet_id, OnboardingPacket.org_id == org_id))
    pkt = res.scalar_one_or_none()
    if not pkt or pkt.status != "verified":
        raise HTTPException(status_code=400, detail="Employee must be verified first")

    await db.execute(text("""
        update public.employees
        set status='active'
        where id=:eid and org_id=:org_id
    """), {"eid": pkt.employee_id, "org_id": actor.org_id})

    pkt.status = "activated"

    await db.commit()

    # 🧠 Payroll + provisioning unlock
    engine.trigger(
        "employee.onboarding.completed",
        {
            "org_id": actor.org_id,
            "employee_id": str(pkt.employee_id)
        }
    )

    return {"status": "employee_activated"}

