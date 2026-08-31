from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.json_utils import json_safe
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
    # Defensive: tables (approval_requests + approval_authority) may not be
    # provisioned in every demo environment. Return an empty list instead of
    # 500 if the schema isn't there yet.
    try:
        rows = (await db.execute(text("""
            select ar.id, ar.title, ar.status, ar.type, ar.amount, ar.requested_by, ar.created_at
            from public.approval_requests ar
            where ar.org_id=:org_id
              and ar.status='pending'
              and exists (
                  select 1
                  from public.approval_authority aa
                  where aa.org_id = ar.org_id
                    and aa.active = true
                    and (
                          ar.amount is null
                       or (ar.amount >= aa.min_amount and ar.amount <= aa.max_amount)
                    )
                    and (
                          (aa.user_id is not null and aa.user_id = :user_id)
                       or (aa.user_id is null and aa.role = :role)
                    )
              )
            order by ar.created_at desc
            limit 100
        """), {"org_id": actor.org_id, "role": actor.role,
               "user_id": actor.user_id})).mappings().all()
        return {"items": [dict(r) for r in rows]}
    except Exception:
        await db.rollback()
        return {"items": [], "note": "approval workflow tables not provisioned"}


# =========================================================
# CHECK AUTHORITY
# =========================================================
async def _check_authority(db: AsyncSession, org_id: str, role: str,
                           amount: float | None, user_id: str | None = None):
    """Amount-tier authorization: an approver may sign off on `amount` iff they
    have an active authority row whose [min_amount, max_amount] window contains
    it. A per-user override (user_id set) takes precedence over the role tier.
    No matching tier -> not authorized (fail closed)."""

    if amount is None:
        return True

    row = (await db.execute(text("""
        select max_amount
        from public.approval_authority
        where org_id = :org_id
          and active = true
          and :amount >= min_amount
          and :amount <= max_amount
          and (
                (user_id is not null and user_id = :user_id)
             or (user_id is null and role = :role)
          )
        order by (user_id is not null) desc   -- prefer a per-user override
        limit 1
    """), {"org_id": org_id, "role": role, "amount": float(amount),
           "user_id": user_id})).first()

    return row is not None


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

    # authority enforcement (amount tier; per-user override wins over role)
    allowed = await _check_authority(db, actor.org_id, actor.role, row["amount"],
                                     user_id=actor.user_id)
    if not allowed:
        # "Exceeds authority level" says the amount was too large for this
        # approver. That is only one of the two ways to get here, and on a fresh
        # deployment it is the wrong one: approval_authority starts empty, so
        # NOBODY can approve anything and every attempt was told the amount was
        # the problem. Distinguish them, because the remedies are different --
        # escalate to a bigger approver, versus configure authority at all.
        configured = (await db.execute(text("""
            select count(*) from public.approval_authority
            where org_id=:org_id and active = true
        """), {"org_id": actor.org_id})).scalar_one()
        if not configured:
            raise HTTPException(
                status_code=403,
                detail=("no approval authority is configured for this organisation, "
                        "so no one can approve this yet. Add an approval_authority "
                        "row granting a role or user an amount band."),
            )
        raise HTTPException(
            status_code=403,
            detail=(f"approving {row['amount']} is above your authority as "
                    f"{actor.role}. Escalate to an approver whose amount band covers it."),
        )

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

