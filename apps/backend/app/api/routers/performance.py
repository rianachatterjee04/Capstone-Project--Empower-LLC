from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from app.core.json_utils import json_safe
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.services.ai import performance_discrepancy_flags
from app.workflow.engine import engine

router = APIRouter(prefix="/performance", tags=["performance"])


# ---------------------------------------------------------
# CREATE REVIEW CYCLE (HR)
# ---------------------------------------------------------
@router.post("/cycles")
async def create_cycle(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="HR only")

    res = await db.execute(text("""
        insert into public.performance_cycles(org_id, name, start_date, end_date, status)
        values (:org_id, :name, :start, :end, 'self_review')
        returning id
    """), {
        "org_id": actor.org_id,
        "name": payload.get("name"),
        "start": payload.get("start_date"),
        "end": payload.get("end_date")
    })

    cycle_id = res.first()[0]
    await db.commit()

    engine.trigger(f"performance_cycle_started:{cycle_id}")

    return {"cycle_id": str(cycle_id)}


# ---------------------------------------------------------
# START REVIEW FOR EMPLOYEE
# ---------------------------------------------------------
@router.post("/{cycle_id}/reviews")
async def create_review(payload: dict, cycle_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("manager","hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Not allowed")

    review_id = uuid.uuid4()

    await db.execute(text("""
        insert into public.performance_reviews(
            id, org_id, employee_id, cycle_id,
            self_review, manager_review, ai_flags, status
        )
        values (:id, :org_id, :emp, :cycle, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'draft')
    """), {
        "id": review_id,
        "org_id": actor.org_id,
        "emp": payload.get("employee_id"),
        "cycle": cycle_id
    })

    await db.commit()
    return {"review_id": str(review_id)}


# ---------------------------------------------------------
# SELF REVIEW
# ---------------------------------------------------------
@router.post("/reviews/{review_id}/self")
async def submit_self(review_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        update public.performance_reviews
        set self_review=:data, status='manager_review'
        where id=:id and org_id=:org_id
    """), {"id": review_id, "org_id": actor.org_id, "data": json.dumps(payload)})

    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# MANAGER REVIEW
# ---------------------------------------------------------
@router.post("/reviews/{review_id}/manager")
async def submit_manager(review_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    flags = await performance_discrepancy_flags(payload.get("self_review"), payload.get("manager_review"))

    await db.execute(text("""
        update public.performance_reviews
        set manager_review=:data, ai_flags=:flags, status='calibration'
        where id=:id and org_id=:org_id
    """), {
        "id": review_id,
        "org_id": actor.org_id,
        "data": json.dumps(payload),
        "flags": json.dumps(flags)
    })

    await db.commit()
    engine.trigger(f"performance_calibration_needed:{review_id}")

    return {"ai_flags": flags}


# ---------------------------------------------------------
# CALIBRATION (HR)
# ---------------------------------------------------------
@router.post("/reviews/{review_id}/calibrate")
async def calibrate(review_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","admin","owner"):
        raise HTTPException(status_code=403, detail="HR only")

    await db.execute(text("""
        update public.performance_reviews
        set calibrated_rating=:rating, status='decision'
        where id=:id and org_id=:org_id
    """), {
        "id": review_id,
        "org_id": actor.org_id,
        "rating": payload.get("rating")
    })

    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# PROMOTION / PIP DECISION
# ---------------------------------------------------------
@router.post("/reviews/{review_id}/decision")
async def decision(review_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Restricted")

    await db.execute(text("""
        update public.performance_reviews
        set outcome=:outcome, status='finalized'
        where id=:id and org_id=:org_id
    """), {
        "id": review_id,
        "org_id": actor.org_id,
        "outcome": payload.get("outcome")
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="performance.finalized",
        entity_type="performance_review",
        entity_id=UUID(review_id),
        payload=payload
    ))

    await db.commit()
    engine.trigger(f"performance_finalized:{review_id}")

    return {"status": "finalized"}


# ---------------------------------------------------------
# VIEW REVIEWS
# ---------------------------------------------------------
@router.get("/reviews")
async def list_reviews(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        select * from public.performance_reviews
        where org_id=:org_id
        order by created_at desc
    """), {"org_id": actor.org_id})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]

