from __future__ import annotations

import uuid
import json
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text


def _as_date(v) -> Optional[date]:
    """Coerce an ISO date string (or date) to a datetime.date for asyncpg.

    asyncpg binds Postgres DATE columns from date objects; a raw ISO string
    raises `'str' object has no attribute 'toordinal'`. None passes through.
    """
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])
from app.core.json_utils import json_safe
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import require_org, db_session, Actor, required_field
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
        # performance_cycles.name is NOT NULL; .get() sent None and the
        # insert failed on the constraint instead of saying what was missing.
        "name": required_field(payload, "name", what="what to call this review cycle"),
        "start": _as_date(payload.get("start_date")),
        "end": _as_date(payload.get("end_date"))
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
        set self_review=cast(:data as jsonb), status='manager_review'
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
        set manager_review=cast(:data as jsonb), ai_flags=cast(:flags as jsonb), status='calibration'
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

    # payload.get("rating") returned None for any body without that exact key,
    # and the update wrote the None straight over calibrated_rating and advanced
    # the review to 'decision' anyway -- answering {"ok": true}. A calibration
    # committee sending the wrong field name silently erased the rating and
    # moved the review on to a promotion decision with nothing behind it.
    #
    # A calibration with no rating is not a calibration.
    rating = required_field(payload, "rating", what="the calibrated rating for this review")

    await db.execute(text("""
        update public.performance_reviews
        set calibrated_rating=:rating, status='decision'
        where id=:id and org_id=:org_id
    """), {
        "id": review_id,
        "org_id": actor.org_id,
        "rating": rating,
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

    _updated = await db.execute(text("""
        update public.performance_reviews
        set outcome=:outcome, status='finalized'
        where id=:id and org_id=:org_id
    """), {
        "id": review_id,
        "org_id": actor.org_id,
        # .get() let a body without "outcome" write NULL and still set the
        # review to 'finalized' -- a promotion/PIP decision recorded as made,
        # with no decision in it.
        "outcome": required_field(payload, "outcome", what="promotion, pip or normal"),
    })
    if _updated.rowcount == 0:
        # The WHERE clause is org-scoped, so zero rows means the id does not
        # belong to this organisation (or does not exist). Continuing wrote an
        # audit event recording an action that never happened, and answered the
        # caller as though it had.
        raise HTTPException(status_code=404, detail="no such review in this organisation")


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

