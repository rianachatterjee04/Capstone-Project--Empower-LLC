from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.json_utils import json_safe
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor, required_field
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
        # Recording findings IS recording an outcome; without it the
        # endpoint writes NULL over whatever was there.
        "outcome": required_field(payload, "outcome", what="what the investigation concluded")
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

    # closure_notes is genuinely optional -- a case may be closed without them --
    # so this does NOT require the field. But writing :notes unconditionally
    # meant closing a case without them erased whatever notes were already
    # recorded. COALESCE keeps what is there when the caller says nothing.
    _updated = await db.execute(text("""
        update public.investigation_cases
        set status='closed', closure_notes = coalesce(:notes, closure_notes)
        where id=:case and org_id=:org_id
    """), {
        "case": case_id,
        "org_id": actor.org_id,
        "notes": payload.get("closure_notes")
    })
    if _updated.rowcount == 0:
        # The WHERE clause is org-scoped, so zero rows means the id does not
        # belong to this organisation (or does not exist). Continuing wrote an
        # audit event recording an action that never happened, and answered the
        # caller as though it had.
        raise HTTPException(status_code=404, detail="no such investigation case in this organisation")


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

