from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth, Actor
from app.db.deps import get_db
from app.db.models import Org, UserProfile, AuditEvent
from app.schemas.orgs import OrgCreate, OrgOut
from app.services.audit import audit_log

router = APIRouter(prefix="/orgs", tags=["orgs"])


# =========================================================
# CREATE ORG (BOOTSTRAP COMPANY GRAPH)
# =========================================================
@router.post("", response_model=OrgOut)
async def create_org(payload: OrgCreate, actor: Actor = Depends(require_auth), db: AsyncSession = Depends(get_db)):

    # Prevent duplicate org memberships during bootstrap
    existing = await db.execute(select(UserProfile).where(UserProfile.user_id == actor.user_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already belongs to an organization")

    org = Org(id=uuid.uuid4(), name=payload.name)
    db.add(org)

    # Owner profile
    profile = UserProfile(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=actor.user_id,
        role="owner",
        display_name=actor.claims.get("user_metadata", {}).get("display_name"),
        email=actor.claims.get("email"),
        manager_user_id=None,
    )
    db.add(profile)

    # ------------------------------------------------------
    # Default company structure (CRITICAL FOR WORKFLOWS)
    # ------------------------------------------------------
    await db.execute(text("""
        insert into public.org_nodes(id, org_id, name, type, parent_id)
        values
        (gen_random_uuid(), :org_id, 'Company', 'root', null),
        (gen_random_uuid(), :org_id, 'Executive', 'department', null),
        (gen_random_uuid(), :org_id, 'Engineering', 'department', null),
        (gen_random_uuid(), :org_id, 'Sales', 'department', null),
        (gen_random_uuid(), :org_id, 'HR', 'department', null),
        (gen_random_uuid(), :org_id, 'Finance', 'department', null)
    """), {"org_id": org.id})

    # ------------------------------------------------------
    # Default approval authority graph
    # ------------------------------------------------------
    await db.execute(text("""
        insert into public.approval_authority(org_id, role, max_amount)
        values
        (:org_id, 'manager', 5000),
        (:org_id, 'director', 25000),
        (:org_id, 'vp', 100000),
        (:org_id, 'cfo', 1000000),
        (:org_id, 'owner', 999999999)
    """), {"org_id": org.id})

    # ------------------------------------------------------
    # Default review cycles
    # ------------------------------------------------------
    await db.execute(text("""
        insert into public.performance_cycles(org_id, name, status)
        values
        (:org_id, 'Annual Review', 'closed'),
        (:org_id, 'Quarterly Check-In', 'closed')
    """), {"org_id": org.id})

    # ------------------------------------------------------
    # Default onboarding checklist template
    # ------------------------------------------------------
    await db.execute(text("""
        insert into public.onboarding_templates(org_id, name, checklist)
        values (
            :org_id,
            'Standard Employee',
            '[
                {"item":"I9 Section 1"},
                {"item":"I9 Section 2"},
                {"item":"W4"},
                {"item":"Direct Deposit"},
                {"item":"Handbook Acknowledgement"},
                {"item":"Security Training"},
                {"item":"Benefits Enrollment"}
            ]'::jsonb
        )
    """), {"org_id": org.id})

    # ------------------------------------------------------
    # Audit
    # ------------------------------------------------------
    await audit_log(db, org.id, actor.user_id, "org.create", "org", str(org.id), {"name": payload.name})

    db.add(AuditEvent(
        org_id=org.id,
        actor_user_id=actor.user_id,
        actor_role="owner",
        event_type="org.bootstrap_complete",
        entity_type="org",
        entity_id=org.id,
        payload={"structure_created": True}
    ))

    await db.commit()
    await db.refresh(org)

    return org


# =========================================================
# LIST USER ORGS
# =========================================================
@router.get("")
async def my_org(actor: Actor = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Org).join(UserProfile).where(UserProfile.user_id == actor.user_id)
    )
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="No organization")
    return org

