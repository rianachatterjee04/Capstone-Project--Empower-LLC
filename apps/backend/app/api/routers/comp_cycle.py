from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.json_utils import json_safe
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
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

    await db.execute(text("""
        insert into public.comp_proposals(
            org_id, cycle_id, employee_id, proposed_salary, proposed_bonus, justification
        )
        values (:org_id, :cycle, :emp, :salary, :bonus, :just)
    """), {
        "org_id": actor.org_id,
        "cycle": cycle_id,
        "emp": payload.get("employee_id"),
        "salary": payload.get("salary"),
        "bonus": payload.get("bonus"),
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

    await db.execute(text("""
        update public.comp_proposals
        set approved_salary=:salary, approved_bonus=:bonus, status='hr_adjusted'
        where org_id=:org_id and cycle_id=:cycle and employee_id=:emp
    """), {
        "org_id": actor.org_id,
        "cycle": cycle_id,
        "emp": payload.get("employee_id"),
        "salary": payload.get("salary"),
        "bonus": payload.get("bonus")
    })

    await db.commit()
    return {"ok": True}


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

    rows = (await db.execute(text("""
        select employee_id, approved_salary, approved_bonus
        from public.comp_proposals
        where cycle_id=:cycle and org_id=:org_id
    """), {"cycle": cycle_id, "org_id": actor.org_id})).mappings().all()

    payroll_payload = [dict(r) for r in rows]
    export_result = export_payroll(payroll_payload)

    await db.execute(text("""
        update public.comp_cycles
        set status='closed'
        where id=:cycle and org_id=:org_id
    """), {"cycle": cycle_id, "org_id": actor.org_id})

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

    res = await db.execute(text("""
        select * from public.comp_proposals
        where cycle_id=:cycle and org_id=:org_id
    """), {"cycle": cycle_id, "org_id": actor.org_id})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]

