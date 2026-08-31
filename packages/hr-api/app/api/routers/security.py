from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.json_utils import json_safe
from uuid import UUID
import hmac
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
async def scim_provision(
    request: Request,
    authorization: str = Header(None),
    db: AsyncSession = Depends(db_session),
):
    """
    Called by identity provider (Okta/Azure AD) when a user is created or updated.

    SECURITY: This is an unattended machine-to-machine endpoint, so it cannot use the
    interactive user JWT (require_org). It MUST instead authenticate with a per-org SCIM
    bearer secret provisioned to the IdP and stored on org_security_settings.scim_secret.
    Previously this endpoint was completely unauthenticated, allowing an anonymous caller
    to upsert an attacker-chosen role (e.g. owner) into any tenant resolved purely by the
    email domain. We now require a valid per-org SCIM credential and bind the org to that
    credential (not just to the email domain).
    """

    body = await request.json()

    external_id = body.get("externalId")
    email = body.get("userName")
    active = body.get("active", True)
    name = body.get("name", {})
    given = name.get("givenName")
    family = name.get("familyName")
    role = body.get("role", "employee")

    if not external_id or not email:
        raise HTTPException(status_code=400, detail="Invalid SCIM payload")

    # Extract the presented SCIM bearer secret.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing SCIM bearer token")
    presented = authorization.split(" ", 1)[1].strip()
    if not presented:
        raise HTTPException(status_code=401, detail="Missing SCIM bearer token")

    # find org by domain
    domain = email.split("@")[-1]

    org = (await db.execute(text("""
        select id from public.org_domains where domain=:domain
    """), {"domain": domain})).first()

    if not org:
        raise HTTPException(status_code=404, detail="No org mapped to domain")

    org_id = org[0]

    # Validate the presented secret against the per-org SCIM credential. Fail closed if
    # no secret is configured for the org (provisioning must be explicitly enabled).
    secret_row = (await db.execute(text("""
        select scim_secret from public.org_security_settings
        where org_id=:org_id
    """), {"org_id": org_id})).first()
    expected_secret = secret_row[0] if secret_row else None
    if not expected_secret or not hmac.compare_digest(presented, str(expected_secret)):
        raise HTTPException(status_code=401, detail="Invalid SCIM credential")

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

    _updated = await db.execute(text("""
        update public.user_profiles
        set last_login_at=now()
        where org_id=:org_id and user_id=:uid
    """), {"org_id": actor.org_id, "uid": actor.user_id})
    if _updated.rowcount == 0:
        # The WHERE clause is org-scoped, so zero rows means the id does not
        # belong to this organisation (or does not exist). Continuing wrote an
        # audit event recording an action that never happened, and answered the
        # caller as though it had.
        raise HTTPException(status_code=404, detail="no such record in this organisation")


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

