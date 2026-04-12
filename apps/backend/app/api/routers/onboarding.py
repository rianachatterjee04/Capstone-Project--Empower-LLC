from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.core.json_utils import json_safe
from uuid import UUID
from datetime import datetime, timedelta

from app.api.deps import require_org, db_session, Actor
from app.api.schemas import OnboardingPacketOut, OnboardingPacketCreate, OnboardingPacketPatch
from app.db.models import OnboardingPacket, Employee, AuditEvent

# 🧠 Behavioral OS
from app.workflow.engine import engine

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ---------------------------------------------------------
# LIST PACKETS
# ---------------------------------------------------------
@router.get("/packets", response_model=list[OnboardingPacketOut])
async def list_packets(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    q = select(OnboardingPacket).where(OnboardingPacket.org_id == org_id).order_by(OnboardingPacket.created_at.desc())
    res = await db.execute(q)
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

