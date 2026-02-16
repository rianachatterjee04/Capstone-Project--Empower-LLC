from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.workflow.engine import engine

router = APIRouter(prefix="/investigations", tags=["investigations"])


# ----------------------------------------------------------
# CREATE CASE (anonymous allowed)
# ----------------------------------------------------------
@router.post("/report")
async def create_case(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    reporter = actor.user_id if actor.role != "anonymous" else None

    res = await db.execute(text("""
        insert into public.investigation_cases(
            org_id, reporter_user_id, accused_employee_id,
            category, description, status
        )
        values (:org_id, :reporter, :accused, :cat, :desc, 'open')
        returning id
    """), {
        "org_id": actor.org_id,
        "reporter": reporter,
        "accused": payload.get("accused_employee_id"),
        "cat": payload.get("category"),
        "desc": payload.get("description")
    })

    case_id = res.first()[0]

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id) if reporter else None,
        actor_role=actor.role,
        event_type="investigation.created",
        entity_type="investigation_case",
        entity_id=case_id,
        payload=payload
    ))

    await db.commit()

    engine.trigger(f"investigation_opened:{case_id}")

    return {"case_id": str(case_id)}


# ----------------------------------------------------------
# ADD WITNESS
# ----------------------------------------------------------
@router.post("/{case_id}/witness")
async def add_witness(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.investigation_witnesses(
            org_id, case_id, employee_id, notes
        )
        values (:org_id, :case, :emp, :notes)
    """), {
        "org_id": actor.org_id,
        "case": case_id,
        "emp": payload.get("employee_id"),
        "notes": payload.get("notes")
    })

    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------
# ADD EVIDENCE
# ----------------------------------------------------------
@router.post("/{case_id}/evidence")
async def add_evidence(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.investigation_evidence(
            org_id, case_id, file_url, description
        )
        values (:org_id, :case, :url, :desc)
    """), {
        "org_id": actor.org_id,
        "case": case_id,
        "url": payload.get("file_url"),
        "desc": payload.get("description")
    })

    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------
# INVESTIGATOR FINDINGS
# ----------------------------------------------------------
@router.post("/{case_id}/findings")
async def add_findings(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","legal","admin","owner"):
        raise HTTPException(status_code=403, detail="Investigators only")

    await db.execute(text("""
        update public.investigation_cases
        set findings=:findings, outcome=:outcome, status='decision_pending'
        where id=:case and org_id=:org_id
    """), {
        "case": case_id,
        "org_id": actor.org_id,
        "findings": payload.get("findings"),
        "outcome": payload.get("outcome")
    })

    engine.trigger(f"investigation_findings:{case_id}")

    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------
# DISCIPLINARY ACTION
# ----------------------------------------------------------
@router.post("/{case_id}/action")
async def disciplinary_action(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","legal","owner"):
        raise HTTPException(status_code=403, detail="Restricted")

    await db.execute(text("""
        insert into public.investigation_actions(
            org_id, case_id, action_type, notes
        )
        values (:org_id, :case, :type, :notes)
    """), {
        "org_id": actor.org_id,
        "case": case_id,
        "type": payload.get("action_type"),
        "notes": payload.get("notes")
    })

    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------
# CLOSE CASE
# ----------------------------------------------------------
@router.post("/{case_id}/close")
async def close_case(case_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","legal","owner"):
        raise HTTPException(status_code=403, detail="Restricted")

    await db.execute(text("""
        update public.investigation_cases
        set status='closed', closure_notes=:notes
        where id=:case and org_id=:org_id
    """), {
        "case": case_id,
        "org_id": actor.org_id,
        "notes": payload.get("closure_notes")
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="investigation.closed",
        entity_type="investigation_case",
        entity_id=UUID(case_id),
        payload=payload
    ))

    await db.commit()

    engine.trigger(f"investigation_closed:{case_id}")

    return {"status": "closed"}

