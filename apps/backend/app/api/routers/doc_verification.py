from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from datetime import datetime, timedelta
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent

router = APIRouter(prefix="/verification", tags=["verification"])


# =========================================================
# REVIEW QUEUE
# =========================================================
@router.get("/queue")
async def queue(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        select *
        from public.documents
        where org_id = :org_id
        and status in ('uploaded','in_review')
        order by created_at asc
    """), {"org_id": actor.org_id})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]


# =========================================================
# ASSIGN REVIEWER
# =========================================================
@router.post("/documents/{doc_id}/assign")
async def assign(doc_id: str, reviewer_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        update public.documents
        set reviewer_employee_id=:rid, status='in_review'
        where id=:id and org_id=:org_id
    """), {"rid": reviewer_id, "id": doc_id, "org_id": actor.org_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="document.assigned",
        entity_type="document",
        entity_id=UUID(doc_id),
        payload={"reviewer": reviewer_id}
    ))

    await db.commit()
    return {"assigned": True}


# =========================================================
# VERIFY / REJECT DOCUMENT
# =========================================================
@router.post("/documents/{doc_id}/verify")
async def verify(doc_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    status = payload.get("status", "verified")
    reason = payload.get("reason")
    expires_days = payload.get("expires_in_days")

    if status not in ("verified","rejected","in_review"):
        raise HTTPException(status_code=400, detail="Invalid status")

    expires_at = None
    if expires_days and status == "verified":
        expires_at = datetime.utcnow() + timedelta(days=int(expires_days))

    await db.execute(text("""
        update public.documents
        set status=:status,
            rejection_reason=:reason,
            expires_at=:expires_at,
            verified_at=now()
        where id=:id and org_id=:org_id
    """), {
        "status": status,
        "reason": reason,
        "expires_at": expires_at,
        "id": doc_id,
        "org_id": actor.org_id
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="document.status_changed",
        entity_type="document",
        entity_id=UUID(doc_id),
        payload={"status": status, "reason": reason, "expires_at": str(expires_at) if expires_at else None}
    ))

    await db.commit()
    return {"ok": True, "status": status}


# =========================================================
# EXPIRING DOCUMENTS ALERT
# =========================================================
@router.get("/expiring")
async def expiring(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session), days: int = 30):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        select id, employee_id, expires_at
        from public.documents
        where org_id=:org_id
        and expires_at is not null
        and expires_at < now() + (:days || ' days')::interval
        order by expires_at asc
    """), {"org_id": actor.org_id, "days": days})

    rows = res.fetchall()

    return [
        {"document_id": str(r[0]), "employee_id": str(r[1]), "expires_at": str(r[2])}
        for r in rows
    ]


# =========================================================
# LOCK DOCUMENT (legal hold)
# =========================================================
@router.post("/documents/{doc_id}/lock")
async def lock(doc_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        update public.documents
        set locked=true
        where id=:id and org_id=:org_id
    """), {"id": doc_id, "org_id": actor.org_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="document.locked",
        entity_type="document",
        entity_id=UUID(doc_id),
        payload={}
    ))

    await db.commit()
    return {"locked": True}

