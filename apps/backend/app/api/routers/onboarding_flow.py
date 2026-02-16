from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.workflow.engine import engine

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ---------------------------------------------------------
# STATES
# ---------------------------------------------------------
VALID_STATES = [
    "offer_sent",
    "offer_accepted",
    "i9_section1_complete",
    "i9_section2_complete",
    "w4_complete",
    "direct_deposit_complete",
    "documents_signed",
    "ready_for_payroll",
    "active_employee"
]


# ---------------------------------------------------------
# CREATE ONBOARDING RECORD (OFFER ACCEPTED)
# ---------------------------------------------------------
@router.post("/start/{employee_id}")
async def start_onboarding(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.onboarding_status(org_id, employee_id, state)
        values (:org_id, :eid, 'offer_accepted')
        on conflict (org_id, employee_id)
        do update set state='offer_accepted'
    """), {"org_id": actor.org_id, "eid": employee_id})

    engine.trigger(f"onboarding_started:{employee_id}")

    await db.commit()
    return {"employee_id": employee_id, "state": "offer_accepted"}


# ---------------------------------------------------------
# ADVANCE STATE
# ---------------------------------------------------------
@router.post("/{employee_id}/advance")
async def advance(employee_id: str, next_state: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if next_state not in VALID_STATES:
        raise HTTPException(status_code=400, detail="Invalid state")

    await db.execute(text("""
        update public.onboarding_status
        set state=:state, updated_at=now()
        where org_id=:org_id and employee_id=:eid
    """), {"state": next_state, "org_id": actor.org_id, "eid": employee_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="onboarding.state_changed",
        entity_type="employee",
        entity_id=UUID(employee_id),
        payload={"state": next_state}
    ))

    engine.trigger(f"onboarding_progress:{employee_id}:{next_state}")

    await db.commit()
    return {"employee_id": employee_id, "state": next_state}


# ---------------------------------------------------------
# I-9 SECTION 1 (EMPLOYEE)
# ---------------------------------------------------------
@router.post("/{employee_id}/i9-section1")
async def i9_section1(employee_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.i9_forms(org_id, employee_id, section, data)
        values (:org_id, :eid, 1, :data::jsonb)
    """), {"org_id": actor.org_id, "eid": employee_id, "data": json.dumps(payload)})

    await advance(employee_id, "i9_section1_complete", actor, db)
    return {"ok": True}


# ---------------------------------------------------------
# I-9 SECTION 2 (EMPLOYER VERIFICATION)
# ---------------------------------------------------------
@router.post("/{employee_id}/i9-section2")
async def i9_section2(employee_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Employer verification required")

    await db.execute(text("""
        insert into public.i9_forms(org_id, employee_id, section, data)
        values (:org_id, :eid, 2, :data::jsonb)
    """), {"org_id": actor.org_id, "eid": employee_id, "data": json.dumps(payload)})

    await advance(employee_id, "i9_section2_complete", actor, db)
    return {"ok": True}


# ---------------------------------------------------------
# W-4 SUBMISSION
# ---------------------------------------------------------
@router.post("/{employee_id}/w4")
async def submit_w4(employee_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.tax_w4(org_id, employee_id, data)
        values (:org_id, :eid, :data::jsonb)
    """), {"org_id": actor.org_id, "eid": employee_id, "data": json.dumps(payload)})

    await advance(employee_id, "w4_complete", actor, db)
    return {"ok": True}


# ---------------------------------------------------------
# DIRECT DEPOSIT
# ---------------------------------------------------------
@router.post("/{employee_id}/direct-deposit")
async def direct_deposit(employee_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if len(payload.get("routing_number","")) != 9:
        raise HTTPException(status_code=400, detail="Invalid routing number")

    await db.execute(text("""
        insert into public.direct_deposits(org_id, employee_id, bank_name, account_last4)
        values (:org_id, :eid, :bank, :last4)
    """), {
        "org_id": actor.org_id,
        "eid": employee_id,
        "bank": payload.get("bank_name"),
        "last4": payload.get("account_number","")[-4:]
    })

    await advance(employee_id, "direct_deposit_complete", actor, db)
    return {"ok": True}


# ---------------------------------------------------------
# FINALIZE — ACTIVATE EMPLOYEE
# ---------------------------------------------------------
@router.post("/{employee_id}/activate")
async def activate(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await advance(employee_id, "active_employee", actor, db)

    engine.trigger(f"employee_activated:{employee_id}")

    return {"employee_id": employee_id, "status": "active"}

