from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from app.core.json_utils import json_safe

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.api.schemas_enterprise import PolicyCreate, PolicyOut
from app.db.models import Policy, AuditEvent
from app.services.policy_dsl import english_to_dsl

router = APIRouter(prefix="/policies", tags=["policies"])

# --- HELPERS ---

def _parse_uuid(value: str, field_name: str) -> UUID:
    """
    Safely converts a string to a UUID. 
    If it fails, it prints the EXACT bad value to your terminal for debugging.
    """
    try:
        if not value:
            raise ValueError("Value is empty")
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        # 🚨 LOOK AT YOUR TERMINAL FOR THIS OUTPUT:
        print(f"\n❌ DEBUG ERROR: '{field_name}' received an invalid value: '{value}' (Type: {type(value)})\n")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid {field_name}: '{value}' is not a valid UUID format."
        )

def _maybe_uuid(value: Optional[str]) -> Optional[UUID]:
    """Helper for optional fields like user_id in audit logs."""
    if not value:
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None

def _policy_to_out(pol: Policy) -> PolicyOut:
    """Maps SQLAlchemy model to Pydantic schema for the frontend."""
    return PolicyOut(
        id=pol.id,
        org_id=pol.org_id,
        name=pol.name,
        body=pol.body,
        dsl=pol.dsl or {},
        version=pol.version,
        status=pol.status,
        created_at=pol.created_at,
    )

# --- ROUTES ---

@router.post("", response_model=PolicyOut)
async def create_policy(
    payload: PolicyCreate,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    org_id = _parse_uuid(actor.org_id, "org_id")
    actor_user_id = _maybe_uuid(actor.user_id)

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
        actor_user_id=actor_user_id,
        actor_role=actor.role,
        event_type="policy.created",
        entity_type="policy",
        entity_id=pol.id,
        payload={"dsl": parsed.dsl, "version": 1},
    ))

    await db.commit()
    await db.refresh(pol)
    return _policy_to_out(pol)


@router.post("/{policy_id}/version", response_model=PolicyOut)
async def new_version(
    policy_id: str,
    payload: PolicyCreate,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    org_id = _parse_uuid(actor.org_id, "org_id")
    actor_user_id = _maybe_uuid(actor.user_id)
    policy_uuid = _parse_uuid(policy_id, "policy_id")

    existing = await db.get(Policy, policy_uuid)
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
    existing.status = "superseded"
    
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_role=actor.role,
        event_type="policy.version_created",
        entity_type="policy",
        entity_id=new_pol.id,
        payload={
            "previous_policy_id": str(existing.id),
            "previous_version": existing.version,
            "new_version": new_pol.version,
        },
    ))

    await db.commit()
    await db.refresh(new_pol)
    return _policy_to_out(new_pol)


@router.post("/{policy_id}/status")
async def change_status(
    policy_id: str,
    status: str = Query(...),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if status not in ("active", "inactive"):
        raise HTTPException(status_code=400, detail="Invalid status: must be active or inactive")

    org_id = _parse_uuid(actor.org_id, "org_id")
    actor_user_id = _maybe_uuid(actor.user_id)
    policy_uuid = _parse_uuid(policy_id, "policy_id")

    pol = await db.get(Policy, policy_uuid)
    if not pol or pol.org_id != org_id:
        raise HTTPException(status_code=404, detail="Policy not found")

    pol.status = status

    db.add(AuditEvent(
        org_id=pol.org_id,
        actor_user_id=actor_user_id,
        actor_role=actor.role,
        event_type="policy.status_changed",
        entity_type="policy",
        entity_id=pol.id,
        payload={"status": status},
    ))

    await db.commit()
    return {"ok": True, "status": status}


@router.get("", response_model=List[PolicyOut])
async def list_policies(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = _parse_uuid(actor.org_id, "org_id")

    res = await db.execute(
        select(Policy)
        .where(Policy.org_id == org_id)
        .order_by(Policy.created_at.desc())
    )

    policies = res.scalars().all()
    return [_policy_to_out(pol) for pol in policies]


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = _parse_uuid(actor.org_id, "org_id")
    policy_uuid = _parse_uuid(policy_id, "policy_id")

    pol = await db.get(Policy, policy_uuid)
    if not pol or pol.org_id != org_id:
        raise HTTPException(status_code=404, detail="Policy not found")

    return _policy_to_out(pol)
