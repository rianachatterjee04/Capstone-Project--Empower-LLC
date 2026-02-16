from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json
from datetime import datetime

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent

router = APIRouter(prefix="/legal", tags=["legal"])


# ---------------------------------------------------------------------------
# LITIGATION HOLD (LEGAL FREEZE)
# Prevents modification of a case and preserves records
# ---------------------------------------------------------------------------
@router.post("/freeze-case/{case_id}")
async def freeze(case_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "admin", "hr", "legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        update public.cases
        set legal_freeze = true
        where id = :id and org_id = :org_id
        returning id
    """), {"id": case_id, "org_id": actor.org_id})

    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")

    # Audit trail (critical for legal defensibility)
    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="legal.freeze",
        entity_type="case",
        entity_id=UUID(case_id),
        payload={"timestamp": datetime.utcnow().isoformat()}
    ))

    await db.commit()
    return {"ok": True, "case_id": case_id, "legal_freeze": True}


# ---------------------------------------------------------------------------
# UNFREEZE (only legal/owner)
# ---------------------------------------------------------------------------
@router.post("/unfreeze-case/{case_id}")
async def unfreeze(case_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "legal"):
        raise HTTPException(status_code=403, detail="Only legal can unfreeze")

    res = await db.execute(text("""
        update public.cases
        set legal_freeze = false
        where id = :id and org_id = :org_id
        returning id
    """), {"id": case_id, "org_id": actor.org_id})

    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="legal.unfreeze",
        entity_type="case",
        entity_id=UUID(case_id),
        payload={}
    ))

    await db.commit()
    return {"ok": True, "case_id": case_id, "legal_freeze": False}


# ---------------------------------------------------------------------------
# EXPORT INVESTIGATION PACKET
# (Structured export — future: generate ZIP w/ docs + hashes)
# ---------------------------------------------------------------------------
@router.get("/export-case/{case_id}")
async def export_case(case_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner", "admin", "hr", "legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    case = (await db.execute(text("""
        select * from public.cases
        where id=:id and org_id=:org_id
    """), {"id": case_id, "org_id": actor.org_id})).mappings().first()

    if not case:
        raise HTTPException(status_code=404, detail="Not found")

    # timeline events
    events = (await db.execute(text("""
        select created_at, event_type, actor_user_id, payload
        from public.audit_events
        where org_id=:org_id and entity_type='case' and entity_id=:id
        order by created_at asc
    """), {"org_id": actor.org_id, "id": case_id})).mappings().all()

    # evidence records
    evidence = (await db.execute(text("""
        select id, storage_path, sha256, created_at
        from public.documents
        where org_id=:org_id and category='investigation' and employee_id=:id
        order by created_at asc
    """), {"org_id": actor.org_id, "id": case_id})).mappings().all()

    packet = {
        "case": dict(case),
        "timeline": [dict(e) for e in events],
        "evidence": [dict(ev) for ev in evidence],
        "generated_at": datetime.utcnow().isoformat(),
        "legal_notice": "This export preserves chain-of-custody metadata. Attachments must be downloaded separately."
    }

    # audit the export
    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="legal.export",
        entity_type="case",
        entity_id=UUID(case_id),
        payload={"exported": True}
    ))

    await db.commit()

    return packet

