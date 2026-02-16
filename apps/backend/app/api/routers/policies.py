from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from uuid import UUID
from datetime import datetime

from app.api.deps import require_org, db_session, Actor
from app.api.schemas_enterprise import PolicyCreate, PolicyOut
from app.db.models import Policy, AuditEvent
from app.services.policy_dsl import english_to_dsl

router = APIRouter(prefix="/policies", tags=["policies"])


# ---------------------------------------------------------
# CREATE NEW POLICY (VERSION 1)
# ---------------------------------------------------------
@router.post("", response_model=PolicyOut)
async def create_policy(
    payload: PolicyCreate,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    parsed = english_to_dsl(payload.name, payload.body)

    pol = Policy(
        org_id=org_id,
        name=parsed.name,
        body=parsed.body,
        dsl=parsed.dsl,
        status="active",
        version=1,
        created_at=datetime.utcnow(),
    )

    db.add(pol)
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="policy.created",
        entity_type="policy",
        entity_id=pol.id,
        payload={"dsl": parsed.dsl, "version": 1}
    ))

    await db.commit()
    await db.refresh(pol)
    return pol


# ---------------------------------------------------------
# CREATE NEW VERSION (IMMUTABLE HISTORY)
# ---------------------------------------------------------
@router.post("/{policy_id}/version", response_model=PolicyOut)
async def new_version(
    policy_id: str,
    payload: PolicyCreate,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    existing = await db.get(Policy, UUID(policy_id))
    if not existing or existing.org_id != org_id:
        raise HTTPException(status_code=404, detail="Policy not found")

    parsed = english_to_dsl(payload.name, payload.body)

    new_pol = Policy(
        org_id=org_id,
        name=parsed.name,
        body=parsed.body,
        dsl=parsed.dsl,
        status="active",
        version=existing.version + 1,
        parent_id=existing.id
    )

    db.add(new_pol)

    # deactivate old version
    existing.status = "superseded"

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="policy.version_created",
        entity_type="policy",
        entity_id=new_pol.id,
        payload={"previous_version": existing.version, "new_version": new_pol.version}
    ))

    await db.commit()
    await db.refresh(new_pol)
    return new_pol


# ---------------------------------------------------------
# ACTIVATE / DEACTIVATE POLICY
# ---------------------------------------------------------
@router.post("/{policy_id}/status")
async def change_status(
    policy_id: str,
    status: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if status not in ("active","inactive"):
        raise HTTPException(status_code=400, detail="Invalid status")

    pol = await db.get(Policy, UUID(policy_id))
    if not pol or str(pol.org_id) != actor.org_id:
        raise HTTPException(status_code=404, detail="Policy not found")

    pol.status = status

    db.add(AuditEvent(
        org_id=pol.org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="policy.status_changed",
        entity_type="policy",
        entity_id=pol.id,
        payload={"status": status}
    ))

    await db.commit()
    return {"ok": True, "status": status}


# ---------------------------------------------------------
# LIST POLICIES
# ---------------------------------------------------------
@router.get("", response_model=list[PolicyOut])
async def list_policies(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session)
):
    org_id = UUID(actor.org_id)

    res = await db.execute(
        select(Policy)
        .where(Policy.org_id == org_id)
        .order_by(Policy.created_at.desc())
    )

    return res.scalars().all()


# ---------------------------------------------------------
# GET SINGLE POLICY
# ---------------------------------------------------------
@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    pol = await db.get(Policy, UUID(policy_id))
    if not pol or str(pol.org_id) != actor.org_id:
        raise HTTPException(status_code=404, detail="Policy not found")

    return pol

