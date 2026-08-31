from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.api.schemas_enterprise import (
    EscalationRuleCreate,
    EscalationRuleOut,
    EscalationOut,
)
from app.core.json_utils import json_safe
from app.db.models import EscalationRule, Escalation, AuditEvent
from app.services.escalation_engine import ensure_case_escalations, escalate_overdue
from app.workflow.engine import engine

router = APIRouter(prefix="/escalations", tags=["escalations"])


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


@router.post("/rules", response_model=EscalationRuleOut)
async def create_rule(
    payload: EscalationRuleCreate,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    payload_dict = payload.model_dump()

    rule = EscalationRule(
        org_id=org_id,
        name=payload_dict.get("name"),
        entity_type=payload_dict.get("entity_type", "case"),
        condition_dsl=payload_dict.get("condition_dsl") or {},
        sla_minutes=payload_dict.get("sla_minutes", 1440),
        route=payload_dict.get("route") or {},
        severity_floor=payload_dict.get("severity_floor", "medium"),
        is_active=payload_dict.get("is_active", True),
    )

    db.add(rule)
    await db.flush()

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="escalation_rule.created",
            entity_type="escalation_rule",
            entity_id=rule.id,
            payload=json_safe(
                {
                    "name": rule.name,
                    "entity_type": rule.entity_type,
                    "condition_dsl": rule.condition_dsl,
                    "sla_minutes": rule.sla_minutes,
                    "route": rule.route,
                    "severity_floor": rule.severity_floor,
                    "is_active": rule.is_active,
                }
            ),
        )
    )

    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/rules", response_model=list[EscalationRuleOut])
async def list_rules(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    rows = (
        await db.execute(
            select(EscalationRule)
            .where(EscalationRule.org_id == org_id)
            .order_by(EscalationRule.created_at.desc())
        )
    ).scalars().all()

    return rows


@router.get("", response_model=list[EscalationOut])
async def list_escalations(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    rows = (
        await db.execute(
            select(Escalation)
            .where(Escalation.org_id == org_id)
            .order_by(Escalation.created_at.desc())
        )
    ).scalars().all()

    return rows


async def apply_escalation_consequences(db: AsyncSession, org_id: UUID):
    rows = (
        await db.execute(
            text(
                """
                select id, entity_id, level
                from public.escalations
                where org_id = :org_id and status = 'active'
                """
            ),
            {"org_id": org_id},
        )
    ).mappings().all()

    for esc in rows:
        target_id = esc["entity_id"]

        case = (
            await db.execute(
                text(
                    """
                    select *
                    from public.cases
                    where id = :id
                    """
                ),
                {"id": target_id},
            )
        ).mappings().first()

        if case:
            await db.execute(
                text(
                    """
                    insert into public.case_snapshots(org_id, case_id, escalation_id, snapshot)
                    values (:org_id, :case_id, :esc_id, cast(:snap as jsonb))
                    """
                ),
                {
                    "org_id": org_id,
                    "case_id": target_id,
                    "esc_id": esc["id"],
                    "snap": json.dumps(json_safe(dict(case))),
                },
            )

        level = str(esc.get("level") or "").lower()

        if level in ("critical", "4", "p1"):
            engine.trigger("legal.freeze_case", {"case_id": str(target_id)})
            engine.trigger("hr.suspend_employee", {"case_id": str(target_id)})
        elif level in ("high", "3", "p2"):
            engine.trigger("hr.notify_hr_lead", {"case_id": str(target_id)})
        elif level in ("medium", "2", "p3"):
            engine.trigger("manager.review_required", {"case_id": str(target_id)})


@router.post("/run")
async def run_escalations(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    created = await ensure_case_escalations(db, org_id)
    bumped = await escalate_overdue(db, org_id)
    await apply_escalation_consequences(db, org_id)
    await db.commit()

    return {"created": created, "bumped": bumped}
