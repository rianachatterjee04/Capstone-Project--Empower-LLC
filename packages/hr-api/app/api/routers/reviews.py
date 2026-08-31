from __future__ import annotations

import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.json_utils import json_safe
from sqlalchemy import text
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.services.ai import performance_discrepancy_flags

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

    # SECURITY: a self-review may only be written for the caller's OWN review. Verify the
    # review's employee_id maps to the caller's employee record (employees.user_id =
    # actor.user_id) before allowing the write, otherwise any org member could overwrite
    # a coworker's self_review by guessing review_id.
    owns = (await db.execute(text("""
        select 1
        from public.performance_reviews pr
        join public.employees e on e.id = pr.employee_id
        where pr.id=:id and pr.org_id=:org_id
          and e.org_id=:org_id and e.user_id=:uid
    """), {"id": review_id, "org_id": actor.org_id, "uid": actor.user_id})).first()

    if not owns:
        raise HTTPException(status_code=403, detail="Not your review")

    await db.execute(text("""
        update public.performance_reviews
        set self_review=cast(:data as jsonb), self_submitted_at=now()
        where id=:id and org_id=:org_id and status='draft'
    """), {"data": json.dumps(responses), "id": review_id, "org_id": actor.org_id})

    await db.commit()
    return {"status": "self_review_saved"}


# =========================================================
# MANAGER REVIEW
# =========================================================
@router.post("/{review_id}/manager")
async def submit_manager(review_id: str, responses: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("manager","hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Manager required")

    # SECURITY: a plain 'manager' may only write the manager_review for an employee they
    # actually manage. hr/admin/owner may act on any review in the org. This prevents an
    # arbitrary manager from overwriting another team's reviews and steering AI finalize.
    if actor.role == "manager":
        manages = (await db.execute(text("""
            select 1
            from public.performance_reviews pr
            join public.employees emp on emp.id = pr.employee_id
            join public.employees mgr on mgr.id = emp.manager_employee_id
            where pr.id=:id and pr.org_id=:org_id
              and emp.org_id=:org_id and mgr.org_id=:org_id
              and mgr.user_id=:uid
        """), {"id": review_id, "org_id": actor.org_id, "uid": actor.user_id})).first()
        if not manages:
            raise HTTPException(status_code=403, detail="You do not manage this employee")

    await db.execute(text("""
        update public.performance_reviews
        set manager_review=cast(:data as jsonb), manager_submitted_at=now(), status='manager_submitted'
        where id=:id and org_id=:org_id
    """), {"data": json.dumps(responses), "id": review_id, "org_id": actor.org_id})

    await db.commit()
    return {"status": "manager_review_saved"}


# =========================================================
# FINALIZE (AI + AUTONOMOUS HR BEHAVIOR)
# =========================================================
@router.post("/{review_id}/finalize")
async def finalize(review_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("manager","hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Manager required")

    # SECURITY: a plain 'manager' may only finalize a review for an employee they actually
    # manage. hr/admin/owner may finalize any review in the org. This mirrors the gate in
    # submit_manager and prevents an arbitrary manager from steering AI finalize.
    if actor.role == "manager":
        manages = (await db.execute(text("""
            select 1
            from public.performance_reviews pr
            join public.employees emp on emp.id = pr.employee_id
            join public.employees mgr on mgr.id = emp.manager_employee_id
            where pr.id=:id and pr.org_id=:org_id
              and emp.org_id=:org_id and mgr.org_id=:org_id
              and mgr.user_id=:uid
        """), {"id": review_id, "org_id": actor.org_id, "uid": actor.user_id})).first()
        if not manages:
            raise HTTPException(status_code=403, detail="You do not manage this employee")

    row = (await db.execute(text("""
        select employee_id, self_review, manager_review
        from public.performance_reviews
        where id=:id and org_id=:org_id and status='manager_submitted'
    """), {"id": review_id, "org_id": actor.org_id})).first()

    if not row:
        raise HTTPException(status_code=404, detail="Review not ready")

    employee_id, self_r, mgr_r = row

    flags = await performance_discrepancy_flags(self_r or {}, mgr_r or {})
    risk = flags

    decision = "normal"
    if risk.get("pip_recommended"):
        decision = "pip"
    elif risk.get("promotion_recommended"):
        decision = "promotion"

    await db.execute(text("""
        update public.performance_reviews
        set ai_flags=cast(:flags as jsonb),
            ai_decision=:decision,
            finalized_at=now(),
            status='finalized'
        where id=:id and org_id=:org_id
    """), {"flags": json.dumps(flags), "decision": decision, "id": review_id, "org_id": actor.org_id})

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
# LIST CYCLES
# =========================================================
@router.get("/cycles")
async def list_cycles(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Real per-org review cycles (open/closed). Lets the UI show whether a cycle
    is actually running rather than inferring one."""
    rows = (await db.execute(text("""
        select name, status, opened_at, closed_at
        from public.performance_cycles
        where org_id=:org_id
        order by opened_at desc nulls last
    """), {"org_id": actor.org_id})).mappings().all()

    return {"cycles": [dict(r) for r in rows]}


# =========================================================
# LIST REVIEWS
# =========================================================
@router.get("")
async def list_reviews(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    # Includes the real per-employee milestone timestamps so the cohort UI can
    # render each employee's true position in the cycle (self → manager →
    # finalized) instead of inferring progress from list order.
    rows = (await db.execute(text("""
        select id, employee_id, cycle, status, ai_decision,
               self_submitted_at, manager_submitted_at, finalized_at
        from public.performance_reviews
        where org_id=:org_id
        order by created_at desc
    """), {"org_id": actor.org_id})).mappings().all()

    return {"reviews": [dict(r) for r in rows]}

