from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from uuid import UUID
import json
import datetime

from app.api.deps import require_org, db_session, Actor
from app.api.schemas_enterprise import EscalationRuleCreate, EscalationRuleOut, EscalationOut
from app.db.models import EscalationRule, Escalation, AuditEvent

from app.services.escalation_engine import ensure_case_escalations, escalate_overdue

# Temporal
from app.temporal.client import get_client
from app.temporal.workflows.escalation import EscalationWorkflow

# NEW: workflow engine
from app.workflow.engine import engine

router = APIRouter(prefix="/escalations", tags=["escalations"])


# ============================================================
# RULE MANAGEMENT
# ============================================================
@router.post("/rules", response_model=EscalationRuleOut)
async def create_rule(payload: EscalationRuleCreate, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    rule = EscalationRule(org_id=org_id, **payload.model_dump())
    db.add(rule)
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="escalation_rule.created",
        entity_type="escalation_rule",
        entity_id=rule.id,
        payload=payload.model_dump()
    ))

    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/rules", response_model=list[EscalationRuleOut])
async def list_rules(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    res = await db.execute(select(EscalationRule).where(EscalationRule.org_id == org_id))
    return res.scalars().all()


# ============================================================
# ESCALATION STATUS
# ============================================================
@router.get("", response_model=list[EscalationOut])
async def list_escalations(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    res = await db.execute(select(Escalation).where(Escalation.org_id == org_id))
    return res.scalars().all()


# ============================================================
# ENTERPRISE ESCALATION RUNNER
# ============================================================
async def apply_escalation_consequences(db: AsyncSession, org_id: UUID):
    """
    This is the legal-grade enforcement layer.
    Turns alerts into actions.
    """

    rows = (await db.execute(text("""
        select id, case_id, level, severity
        from public.escalations
        where org_id=:org_id and status='active'
    """), {"org_id": str(org_id)})).mappings().all()

    for esc in rows:

        # snapshot case at time of escalation
        case = (await db.execute(text("""
            select * from public.cases where id=:id
        """), {"id": esc["case_id"]})).mappings().first()

        if case:
            await db.execute(text("""
                insert into public.case_snapshots(org_id, case_id, escalation_id, snapshot)
                values (:org_id, :case_id, :esc_id, :snap::jsonb)
            """), {
                "org_id": str(org_id),
                "case_id": esc["case_id"],
                "esc_id": esc["id"],
                "snap": json.dumps(dict(case))
            })

        # consequence binding
        if esc["severity"] == "critical":
            engine.trigger("legal.freeze_case", {"case_id": esc["case_id"]})
            engine.trigger("hr.suspend_employee", {"case_id": esc["case_id"]})

        elif esc["severity"] == "high":
            engine.trigger("hr.notify_hr_lead", {"case_id": esc["case_id"]})

        elif esc["severity"] == "medium":
            engine.trigger("manager.review_required", {"case_id": esc["case_id"]})


# ============================================================
# MANUAL RUN
# ============================================================
@router.post("/run")
async def run_escalations(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    created = await ensure_case_escalations(db, org_id)
    bumped = await escalate_overdue(db, org_id)

    await apply_escalation_consequences(db, org_id)

    return {"created": created, "bumped": bumped}


# ============================================================
# TEMPORAL WORKER
# ============================================================
@router.post("/schedule")
async def schedule_escalation_worker(actor: Actor = Depends(require_org)):

    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    client = await get_client()

    handle = await client.start_workflow(
        EscalationWorkflow.run,
        actor.org_id,
        id=f"escalation-worker-{actor.org_id}",
        task_queue="foundry-people",
    )

    return {"workflow_id": handle.id, "status": "scheduled"}

