from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.json_utils import json_safe
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.workflow.engine import engine  # triggers downstream workflows

router = APIRouter(prefix="/approvals", tags=["approvals"])


# -------------------------------------------------------
# LIST PENDING APPROVALS
# -------------------------------------------------------
@router.get("/pending")
async def pending(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    rows = (await db.execute(text("""
        select id, title, status, requested_by, created_at
        from public.approval_requests
        where org_id=:org_id and status='pending'
        order by created_at desc
        limit 100
    """), {"org_id": actor.org_id})).mappings().all()

    return {"items": [dict(r) for r in rows]}


# -------------------------------------------------------
# APPROVE
# -------------------------------------------------------
@router.post("/{approval_id}/approve")
async def approve(approval_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    # update status
    res = await db.execute(text("""
        update public.approval_requests
        set status='approved'
        where id=:id and org_id=:org_id and status='pending'
        returning id, type
    """), {"id": approval_id, "org_id": actor.org_id})

    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found or already processed")

    # record action
    await db.execute(text("""
        insert into public.approval_actions(org_id, approval_request_id, actor_user_id, actor_role, action)
        values (:org_id, :rid, :uid, :role, 'approved')
    """), {"org_id": actor.org_id, "rid": approval_id, "uid": actor.user_id, "role": actor.role})

    # audit
    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="approval.approved",
        entity_type="approval_request",
        entity_id=UUID(approval_id),
        payload={}
    ))

    await db.commit()

    # trigger workflow automation
    engine.trigger(f"approval_approved:{row['type']}")

    return {"ok": True}


# -------------------------------------------------------
# REJECT
# -------------------------------------------------------
@router.post("/{approval_id}/reject")
async def reject(approval_id: str, reason: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        update public.approval_requests
        set status='rejected'
        where id=:id and org_id=:org_id and status='pending'
        returning id, type
    """), {"id": approval_id, "org_id": actor.org_id})

    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found or already processed")

    await db.execute(text("""
        insert into public.approval_actions(org_id, approval_request_id, actor_user_id, actor_role, action, notes)
        values (:org_id, :rid, :uid, :role, 'rejected', :reason)
    """), {"org_id": actor.org_id, "rid": approval_id, "uid": actor.user_id, "role": actor.role, "reason": reason})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="approval.rejected",
        entity_type="approval_request",
        entity_id=UUID(approval_id),
        payload={"reason": reason}
    ))

    await db.commit()

    engine.trigger(f"approval_rejected:{row['type']}")

    return {"ok": True}

