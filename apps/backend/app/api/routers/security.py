from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import secrets

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent

router = APIRouter(prefix="/security", tags=["security"])


# ============================================================
# SSO SETTINGS
# ============================================================
@router.get("/sso/status")
async def sso_status(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    row = (await db.execute(text("""
        select sso_enabled, idp_name
        from public.org_security_settings
        where org_id=:org_id
    """), {"org_id": actor.org_id})).first()

    if not row:
        return {"enabled": False}

    return {"enabled": row[0], "provider": row[1]}


@router.post("/sso/enable")
async def enable_sso(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Owner required")

    await db.execute(text("""
        insert into public.org_security_settings(org_id, sso_enabled, idp_name)
        values (:org_id, true, :idp)
        on conflict (org_id) do update set sso_enabled=true, idp_name=:idp
    """), {"org_id": actor.org_id, "idp": payload.get("provider","okta")})

    await db.commit()
    return {"enabled": True}


@router.post("/sso/disable")
async def disable_sso(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Owner required")

    await db.execute(text("""
        update public.org_security_settings set sso_enabled=false
        where org_id=:org_id
    """), {"org_id": actor.org_id})

    await db.commit()
    return {"enabled": False}


# ============================================================
# SCIM USER PROVISIONING (Okta/Azure AD)
# ============================================================
@router.post("/scim/provision")
async def scim_provision(request: Request, db: AsyncSession = Depends(db_session)):
    """
    Called by identity provider when user created or updated.
    """

    body = await request.json()

    external_id = body.get("externalId")
    email = body.get("userName")
    active = body.get("active", True)
    name = body.get("name", {})
    given = name.get("givenName")
    family = name.get("familyName")
    role = body.get("role","employee")

    if not external_id or not email:
        raise HTTPException(status_code=400, detail="Invalid SCIM payload")

    # find org by domain
    domain = email.split("@")[-1]

    org = (await db.execute(text("""
        select id from public.org_domains where domain=:domain
    """), {"domain": domain})).first()

    if not org:
        raise HTTPException(status_code=404, detail="No org mapped to domain")

    org_id = org[0]

    # upsert user
    await db.execute(text("""
        insert into public.user_profiles(org_id, external_id, email, role, active, first_name, last_name)
        values (:org_id, :external_id, :email, :role, :active, :fn, :ln)
        on conflict (org_id, external_id)
        do update set email=:email, role=:role, active=:active, first_name=:fn, last_name=:ln
    """), {
        "org_id": org_id,
        "external_id": external_id,
        "email": email,
        "role": role,
        "active": active,
        "fn": given,
        "ln": family
    })

    await db.commit()

    return {"status": "provisioned"}


# ============================================================
# SCIM DEPROVISION
# ============================================================
@router.post("/scim/deprovision/{external_id}")
async def scim_deprovision(external_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        update public.user_profiles
        set active=false
        where org_id=:org_id and external_id=:external_id
    """), {"org_id": actor.org_id, "external_id": external_id})

    await db.commit()
    return {"status": "deactivated"}


# ============================================================
# LOGIN TRACKING (Audit requirement)
# ============================================================
@router.post("/login-record")
async def record_login(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        update public.user_profiles
        set last_login_at=now()
        where org_id=:org_id and user_id=:uid
    """), {"org_id": actor.org_id, "uid": actor.user_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="security.login",
        entity_type="user",
        entity_id=UUID(actor.user_id),
        payload={}
    ))

    await db.commit()

    return {"recorded": True}

