from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.json_utils import json_safe
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor, required_field
from app.db.models import AuditEvent
from app.workflow.engine import engine
from app.services.payroll_export import export_payroll

router = APIRouter(prefix="/compcycle", tags=["compensation"])


# ------------------------------------------------------------
# START COMPENSATION CYCLE (HR)
# ------------------------------------------------------------
@router.post("/start")
async def start_cycle(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        insert into public.comp_cycles(org_id, name, budget, status)
        values (:org_id, :name, :budget, 'planning')
        returning id
    """), {
        "org_id": actor.org_id,
        "name": payload.get("name"),
        "budget": payload.get("budget")
    })

    cycle_id = res.first()[0]

    await db.commit()
    return {"cycle_id": str(cycle_id)}


# ------------------------------------------------------------
# MANAGER PROPOSAL
# ------------------------------------------------------------
@router.post("/{cycle_id}/propose")
async def propose(payload: dict, cycle_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("manager","hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Not allowed")

    # Every field here was read with .get(), so POSTing {} stored a proposal
    # with a null employee, a null salary and a null bonus -- a pay decision
    # about nobody, for no amount. Finalize then counted it and reported it as
    # an exported payroll record.
    #
    # Nothing crashed, which is why it survived: unlike a raw payload["x"], a
    # .get() on a missing key is silent. For an optional field that is correct.
    # For the person a raise belongs to, it is not.
    employee_id = required_field(payload, "employee_id", what="who this proposal is for")
    salary = payload.get("salary")
    bonus = payload.get("bonus")
    if salary is None and bonus is None:
        raise HTTPException(
            status_code=422,
            detail="a proposal must set 'salary' or 'bonus'; one that changes neither is not a proposal",
        )

    await db.execute(text("""
        insert into public.comp_proposals(
            org_id, cycle_id, employee_id, proposed_salary, proposed_bonus, justification
        )
        values (:org_id, :cycle, :emp, :salary, :bonus, :just)
    """), {
        "org_id": actor.org_id,
        "cycle": cycle_id,
        "emp": employee_id,
        "salary": salary,
        "bonus": bonus,
        "just": payload.get("justification")
    })

    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------
# HR ADJUSTMENT
# ------------------------------------------------------------
@router.post("/{cycle_id}/adjust")
async def adjust(payload: dict, cycle_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","admin","owner"):
        raise HTTPException(status_code=403, detail="HR only")

    # Three defects in one statement.
    #
    # employee_id came from .get(), so a body without it made the WHERE clause
    # `employee_id = NULL`, which matches no row. The update changed nothing and
    # still answered {"ok": true} -- an HR adjuster is told their change landed
    # when it did not.
    #
    # salary and bonus were both written unconditionally, so adjusting only the
    # salary wrote NULL over an already-approved bonus. COALESCE keeps whatever
    # is not being changed.
    #
    # And an adjust that supplies neither is not an adjustment.
    employee_id = required_field(payload, "employee_id", what="whose proposal to adjust")
    salary = payload.get("salary")
    bonus = payload.get("bonus")
    if salary is None and bonus is None:
        raise HTTPException(
            status_code=422,
            detail="an adjustment must set 'salary' or 'bonus'; supplying neither changes nothing",
        )

    result = await db.execute(text("""
        update public.comp_proposals
        set approved_salary = coalesce(:salary, approved_salary),
            approved_bonus  = coalesce(:bonus,  approved_bonus),
            status='hr_adjusted'
        where org_id=:org_id and cycle_id=:cycle and employee_id=:emp
    """), {
        "org_id": actor.org_id,
        "cycle": cycle_id,
        "emp": employee_id,
        "salary": salary,
        "bonus": bonus,
    })

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="no proposal for that employee in this cycle -- nothing was changed",
        )

    await db.commit()
    return {"ok": True, "adjusted": result.rowcount}


# ------------------------------------------------------------
# SUBMIT FOR APPROVAL
# ------------------------------------------------------------
@router.post("/{cycle_id}/submit")
async def submit_for_approval(cycle_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","admin","owner"):
        raise HTTPException(status_code=403, detail="HR only")

    await db.execute(text("""
        update public.comp_cycles
        set status='approval'
        where id=:cycle and org_id=:org_id
    """), {"cycle": cycle_id, "org_id": actor.org_id})

    engine.trigger(f"comp_cycle_submitted:{cycle_id}")

    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------
# FINALIZE (AFTER APPROVAL)
# ------------------------------------------------------------
@router.post("/{cycle_id}/finalize")
async def finalize_cycle(cycle_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin"):
        raise HTTPException(status_code=403, detail="Executive only")

    # This selected EVERY proposal in the cycle, whatever its state, and handed
    # the lot to payroll -- including ones still sitting at 'proposed' with a
    # null approved_salary and a null approved_bonus. Closing a merit cycle
    # would have pushed pay changes nobody had approved, for amounts nobody had
    # set.
    #
    # Only decisions with an approved amount go. The rest are counted and named
    # in the response, because a decision silently dropped from a comp cycle is
    # somebody's raise going missing.
    rows = (await db.execute(text("""
        select employee_id, approved_salary, approved_bonus, status
        from public.comp_proposals
        where cycle_id=:cycle and org_id=:org_id
    """), {"cycle": cycle_id, "org_id": actor.org_id})).mappings().all()

    approved = [
        dict(r) for r in rows
        if r["approved_salary"] is not None or r["approved_bonus"] is not None
    ]
    unapproved = [
        r for r in rows
        if r["approved_salary"] is None and r["approved_bonus"] is None
    ]

    export_result = export_payroll(approved)
    export_result["not_approved"] = len(unapproved)
    if unapproved:
        export_result["not_approved_note"] = (
            f"{len(unapproved)} proposal(s) in this cycle have no approved salary or "
            f"bonus and were NOT included. Run adjust on them before finalising, or "
            f"they take effect for nobody."
        )

    _closed = await db.execute(text("""
        update public.comp_cycles
        set status='closed'
        where id=:cycle and org_id=:org_id
    """), {"cycle": cycle_id, "org_id": actor.org_id})
    if _closed.rowcount == 0:
        # Org-scoped WHERE: zero rows means this cycle is not this organisation's.
        # Continuing recorded an audit event for a cycle that was never closed.
        raise HTTPException(status_code=404, detail="no such comp cycle in this organisation")

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="comp_cycle.finalized",
        entity_type="comp_cycle",
        entity_id=UUID(cycle_id),
        payload={"export": export_result}
    ))

    await db.commit()

    return {
        "status": "closed",
        "payroll_export": export_result
    }


# ------------------------------------------------------------
# VIEW CYCLE
# ------------------------------------------------------------
@router.get("/{cycle_id}")
async def view_cycle(cycle_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    # SECURITY: comp proposals expose every coworker's salaries/bonuses/justifications.
    # Restrict reads to privileged roles, matching the role gating on the write endpoints
    # in this file; a plain 'employee' must not be able to enumerate the whole org's comp.
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        select * from public.comp_proposals
        where cycle_id=:cycle and org_id=:org_id
    """), {"cycle": cycle_id, "org_id": actor.org_id})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]

