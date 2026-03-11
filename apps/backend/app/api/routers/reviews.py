from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.json_utils import json_safe
from sqlalchemy import text
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.services.ai import performance_discrepancy_flags, performance_risk_assessment

# 🧠 Behavioral OS
from app.workflow.engine import engine

router = APIRouter(prefix="/reviews", tags=["reviews"])


# =========================================================
# REVIEW CYCLE MANAGEMENT
# =========================================================

@router.post("/cycle/open")
async def open_cycle(name: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        insert into public.performance_cycles(org_id, name, status, opened_at)
        values (:org_id, :name, 'open', now())
    """), {"org_id": actor.org_id, "name": name})

    await db.commit()
    return {"cycle_opened": name}


@router.post("/cycle/close")
async def close_cycle(name: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        update public.performance_cycles
        set status='closed', closed_at=now()
        where org_id=:org_id and name=:name
    """), {"org_id": actor.org_id, "name": name})

    await db.commit()
    return {"cycle_closed": name}


# =========================================================
# CREATE REVIEW
# =========================================================
@router.post("/create")
async def create_review(employee_id: str, cycle: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    cycle_status = (await db.execute(text("""
        select status from public.performance_cycles
        where org_id=:org_id and name=:cycle
    """), {"org_id": actor.org_id, "cycle": cycle})).first()

    if not cycle_status or cycle_status[0] != "open":
        raise HTTPException(status_code=400, detail="Cycle not open")

    review_id = str(uuid.uuid4())

    await db.execute(text("""
        insert into public.performance_reviews(id, org_id, employee_id, cycle, status, created_at)
        values (:id, :org_id, :employee_id, :cycle, 'draft', now())
    """), {
        "id": review_id,
        "org_id": actor.org_id,
        "employee_id": employee_id,
        "cycle": cycle
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="review.created",
        entity_type="performance_review",
        entity_id=UUID(review_id),
        payload={"cycle": cycle}
    ))

    await db.commit()
    return {"review_id": review_id}


# =========================================================
# SELF REVIEW
# =========================================================
@router.post("/{review_id}/self")
async def submit_self(review_id: str, responses: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        update public.performance_reviews
        set self_review=:data::jsonb, self_submitted_at=now()
        where id=:id and org_id=:org_id and status='draft'
    """), {"data": responses, "id": review_id, "org_id": actor.org_id})

    await db.commit()
    return {"status": "self_review_saved"}


# =========================================================
# MANAGER REVIEW
# =========================================================
@router.post("/{review_id}/manager")
async def submit_manager(review_id: str, responses: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("manager","hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Manager required")

    await db.execute(text("""
        update public.performance_reviews
        set manager_review=:data::jsonb, manager_submitted_at=now(), status='manager_submitted'
        where id=:id and org_id=:org_id
    """), {"data": responses, "id": review_id, "org_id": actor.org_id})

    await db.commit()
    return {"status": "manager_review_saved"}


# =========================================================
# FINALIZE (AI + AUTONOMOUS HR BEHAVIOR)
# =========================================================
@router.post("/{review_id}/finalize")
async def finalize(review_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    row = (await db.execute(text("""
        select employee_id, self_review, manager_review
        from public.performance_reviews
        where id=:id and org_id=:org_id and status='manager_submitted'
    """), {"id": review_id, "org_id": actor.org_id})).first()

    if not row:
        raise HTTPException(status_code=404, detail="Review not ready")

    employee_id, self_r, mgr_r = row

    flags = await performance_discrepancy_flags(self_r or {}, mgr_r or {})
    risk = await performance_risk_assessment(self_r or {}, mgr_r or {})

    decision = "normal"
    if risk.get("pip_recommended"):
        decision = "pip"
    elif risk.get("promotion_recommended"):
        decision = "promotion"

    await db.execute(text("""
        update public.performance_reviews
        set ai_flags=:flags::jsonb,
            ai_decision=:decision,
            finalized_at=now(),
            status='finalized'
        where id=:id
    """), {"flags": flags, "decision": decision, "id": review_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="review.finalized",
        entity_type="performance_review",
        entity_id=UUID(review_id),
        payload={"ai_flags": flags, "decision": decision}
    ))

    await db.commit()

    # 🧠 THIS IS THE AUTONOMOUS HR MOMENT
    engine.trigger(
        "performance.review.finalized",
        {
            "org_id": actor.org_id,
            "review_id": review_id,
            "employee_id": str(employee_id),
            "decision": decision,
            "ai_flags": flags
        }
    )

    return {"finalized": True, "ai_flags": flags, "decision": decision}


# =========================================================
# CALIBRATION VIEW (HR)
# =========================================================
@router.get("/calibration/{cycle}")
async def calibration(cycle: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rows = (await db.execute(text("""
        select employee_id, ai_decision, manager_review
        from public.performance_reviews
        where org_id=:org_id and cycle=:cycle and status='finalized'
    """), {"org_id": actor.org_id, "cycle": cycle})).mappings().all()

    return {"calibration": [dict(r) for r in rows]}


# =========================================================
# LIST REVIEWS
# =========================================================
@router.get("")
async def list_reviews(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    rows = (await db.execute(text("""
        select id, employee_id, cycle, status, ai_decision
        from public.performance_reviews
        where org_id=:org_id
        order by created_at desc
    """), {"org_id": actor.org_id})).mappings().all()

    return {"reviews": [dict(r) for r in rows]}

