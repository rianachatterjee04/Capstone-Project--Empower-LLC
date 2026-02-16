from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.api.schemas import CaseOut, CaseCreate
from app.db.models import Case, AuditEvent

# 🧠 Behavioral OS
from app.workflow.engine import engine

router = APIRouter(prefix="/cases", tags=["cases"])


# =========================================================
# CREATE CASE (anonymous reporting / ombudsman)
# =========================================================
@router.post("", response_model=CaseOut)
async def create_case(payload: CaseCreate, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    org_id = UUID(actor.org_id)

    item = Case(
        org_id=org_id,
        reporter_employee_id=payload.reporter_employee_id,
        is_anonymous=payload.is_anonymous,
        category=payload.category,
        severity=payload.severity,
        details=payload.details,
        status="reported"
    )

    db.add(item)
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="case.created",
        entity_type="case",
        entity_id=item.id,
        payload=payload.model_dump()
    ))

    await db.commit()
    await db.refresh(item)

    # 🧠 AI escalation
    engine.trigger(
        "case.created",
        {
            "org_id": actor.org_id,
            "case_id": str(item.id),
            "severity": item.severity,
            "anonymous": item.is_anonymous,
            "category": item.category
        }
    )

    return item


# =========================================================
# LIST CASES
# =========================================================
@router.get("", response_model=list[CaseOut])
async def list_cases(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    q = select(Case).where(Case.org_id == org_id).order_by(Case.created_at.desc())
    res = await db.execute(q)
    return res.scalars().all()


# =========================================================
# ASSIGN INVESTIGATOR
# =========================================================
@router.post("/{case_id}/assign")
async def assign(case_id: str, investigator_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        update public.cases
        set investigator_employee_id=:inv, status='assigned'
        where org_id=:org and id=:cid
    """), {"org": actor.org_id, "cid": case_id, "inv": investigator_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="case.assigned",
        entity_type="case",
        entity_id=UUID(case_id),
        payload={"investigator": investigator_id}
    ))

    await db.commit()

    engine.trigger(
        "case.assigned",
        {"org_id": actor.org_id, "case_id": case_id}
    )

    return {"assigned": True}


# =========================================================
# ADD EVIDENCE
# =========================================================
@router.post("/{case_id}/evidence")
async def add_evidence(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.case_evidence(org_id, case_id, added_by, description, metadata)
        values (:org, :cid, :uid, :desc, :meta::jsonb)
    """), {
        "org": actor.org_id,
        "cid": case_id,
        "uid": actor.user_id,
        "desc": payload.get("description"),
        "meta": json.dumps(payload.get("metadata", {}))
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="case.evidence_added",
        entity_type="case",
        entity_id=UUID(case_id),
        payload=payload
    ))

    await db.commit()

    engine.trigger(
        "case.evidence_added",
        {"org_id": actor.org_id, "case_id": case_id}
    )

    return {"added": True}


# =========================================================
# RECORD FINDINGS
# =========================================================
@router.post("/{case_id}/findings")
async def findings(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        update public.cases
        set findings=:findings::jsonb, status='findings_recorded'
        where org_id=:org and id=:cid
    """), {
        "org": actor.org_id,
        "cid": case_id,
        "findings": json.dumps(payload)
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="case.findings_recorded",
        entity_type="case",
        entity_id=UUID(case_id),
        payload=payload
    ))

    await db.commit()

    engine.trigger(
        "case.findings_recorded",
        {"org_id": actor.org_id, "case_id": case_id}
    )

    return {"recorded": True}


# =========================================================
# DISCIPLINARY ACTION
# =========================================================
@router.post("/{case_id}/action")
async def action(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        insert into public.case_actions(org_id, case_id, action_type, notes, created_by)
        values (:org, :cid, :type, :notes, :uid)
    """), {
        "org": actor.org_id,
        "cid": case_id,
        "type": payload.get("type"),
        "notes": payload.get("notes"),
        "uid": actor.user_id
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="case.action_taken",
        entity_type="case",
        entity_id=UUID(case_id),
        payload=payload
    ))

    await db.commit()

    engine.trigger(
        "case.action_taken",
        {"org_id": actor.org_id, "case_id": case_id}
    )

    return {"action_recorded": True}


# =========================================================
# CLOSE CASE
# =========================================================
@router.post("/{case_id}/close")
async def close_case(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        update public.cases
        set status='closed', closure_reason=:reason
        where org_id=:org and id=:cid
    """), {
        "org": actor.org_id,
        "cid": case_id,
        "reason": payload.get("reason")
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="case.closed",
        entity_type="case",
        entity_id=UUID(case_id),
        payload=payload
    ))

    await db.commit()

    engine.trigger(
        "case.closed",
        {"org_id": actor.org_id, "case_id": case_id}
    )

    return {"closed": True}

