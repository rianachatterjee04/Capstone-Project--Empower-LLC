from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.workflow.engine import engine

router = APIRouter(prefix="/approvals", tags=["approvals"])


# =========================================================
# LIST MY PENDING APPROVALS (scoped by authority)
# =========================================================
@router.get("/pending")
async def pending(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    rows = (await db.execute(text("""
        select ar.id, ar.title, ar.status, ar.type, ar.amount, ar.requested_by, ar.created_at
        from public.approval_requests ar
        join public.approval_authority aa on aa.org_id=ar.org_id
        where ar.org_id=:org_id
          and ar.status='pending'
          and (
              aa.role=:role
              or :role='owner'
          )
        order by ar.created_at desc
        limit 100
    """), {"org_id": actor.org_id, "role": actor.role})).mappings().all()

    return {"items": [dict(r) for r in rows]}


# =========================================================
# CHECK AUTHORITY
# =========================================================
async def _check_authority(db: AsyncSession, org_id: str, role: str, amount: float | None):

    if amount is None:
        return True

    row = (await db.execute(text("""
        select max_amount
        from public.approval_authority
        where org_id=:org_id and role=:role
    """), {"org_id": org_id, "role": role})).first()

    if not row:
        return False

    return float(amount) <= float(row[0])


# =========================================================
# APPROVE
# =========================================================
@router.post("/{approval_id}/approve")
async def approve(approval_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    # fetch approval
    row = (await db.execute(text("""
        select id, type, amount, status
        from public.approval_requests
        where id=:id and org_id=:org_id
    """), {"id": approval_id, "org_id": actor.org_id})).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    if row["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already processed")

    # authority enforcement
    allowed = await _check_authority(db, actor.org_id, actor.role, row["amount"])
    if not allowed:
        raise HTTPException(status_code=403, detail="Approval exceeds authority level")

    # approve
    await db.execute(text("""
        update public.approval_requests
        set status='approved', approved_by=:uid, approved_role=:role, approved_at=now()
        where id=:id
    """), {"id": approval_id, "uid": actor.user_id, "role": actor.role})

    await db.execute(text("""
        insert into public.approval_actions(org_id, approval_request_id, actor_user_id, actor_role, action)
        values (:org_id, :rid, :uid, :role, 'approved')
    """), {"org_id": actor.org_id, "rid": approval_id, "uid": actor.user_id, "role": actor.role})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="approval.approved",
        entity_type="approval_request",
        entity_id=UUID(approval_id),
        payload={"amount": row["amount"], "type": row["type"]}
    ))

    await db.commit()

    # downstream automation
    engine.trigger(f"approval.approved.{row['type']}", {"approval_id": approval_id})

    return {"ok": True}


# =========================================================
# REJECT
# =========================================================
@router.post("/{approval_id}/reject")
async def reject(approval_id: str, reason: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    row = (await db.execute(text("""
        select id, type, status
        from public.approval_requests
        where id=:id and org_id=:org_id
    """), {"id": approval_id, "org_id": actor.org_id})).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    if row["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already processed")

    await db.execute(text("""
        update public.approval_requests
        set status='rejected', rejected_at=now()
        where id=:id
    """), {"id": approval_id})

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

    engine.trigger(f"approval.rejected.{row['type']}", {"approval_id": approval_id})

    return {"ok": True}


# =========================================================
# CREATE APPROVAL REQUEST (used by other modules)
# =========================================================
@router.post("/request")
async def create_request(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """
    Modules call this instead of inserting approval directly.
    Enables cross-module workflows.
    """

    res = await db.execute(text("""
        insert into public.approval_requests(org_id, title, type, amount, requested_by, status)
        values (:org_id, :title, :type, :amount, :uid, 'pending')
        returning id
    """), {
        "org_id": actor.org_id,
        "title": payload.get("title"),
        "type": payload.get("type"),
        "amount": payload.get("amount"),
        "uid": actor.user_id
    })

    approval_id = res.first()[0]

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="approval.requested",
        entity_type="approval_request",
        entity_id=approval_id,
        payload=payload
    ))

    await db.commit()

    engine.trigger("approval.created", {"approval_id": str(approval_id), "type": payload.get("type")})

    return {"approval_id": str(approval_id)}

