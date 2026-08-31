from __future__ import annotations

import datetime
import json
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.core.config import settings
from app.integrations.common import verify_hmac_sha256
from app.integrations.lever_oauth import build_auth_url as lever_build_auth_url
from app.integrations.lever_oauth import exchange_code as lever_exchange_code
from app.integrations.linkedin import LinkedInClient
from app.integrations.salary_dot_com import SalaryDotComClient
from app.integrations.store import (
    get_connection,
    upsert_connection_secret,
    upsert_connection_tokens,
)
from app.temporal.client import get_client
from app.temporal.workflows.replay import IntegrationReplayWorkflow
from app.temporal.workflows.sync import IntegrationSyncWorkflow
from app.workflow.engine import engine

router = APIRouter(prefix="/integrations", tags=["integrations"])

SUPPORTED = ["greenhouse", "lever", "linkedin", "salarydotcom"]


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return None


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("select to_regclass(:table_name)"),
        {"table_name": f"public.{table_name}"},
    )
    return result.scalar() is not None


# ============================================================
# EVENT ROUTING
# ============================================================
async def route_event(
    db: AsyncSession,
    org_id: str,
    provider: str,
    event_type: str | None,
    payload: dict,
):
    if event_type in ("candidate.hired", "hire", "application_hired"):
        engine.trigger(
            "employee.hired",
            {
                "org_id": org_id,
                "provider": provider,
                "payload": payload,
            },
        )

    if event_type in ("candidate.rejected", "application_rejected"):
        engine.trigger(
            "candidate.rejected",
            {
                "org_id": org_id,
                "provider": provider,
                "payload": payload,
            },
        )

    if event_type in ("offer.created", "offer_opened"):
        engine.trigger(
            "offer.created",
            {
                "org_id": org_id,
                "provider": provider,
                "payload": payload,
            },
        )

    if event_type in ("job.created", "opening.created"):
        engine.trigger(
            "headcount.plan.changed",
            {
                "org_id": org_id,
                "provider": provider,
                "payload": payload,
            },
        )

    engine.trigger(
        "integration.sync.completed",
        {
            "org_id": org_id,
            "provider": provider,
            "event_type": event_type,
        },
    )


# ============================================================
# PROVIDERS
# ============================================================
@router.get("/providers")
async def providers(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    items = []
    connected = {p: False for p in SUPPORTED}

    if await table_exists(db, "integration_connections"):
        rows = (
            await db.execute(
                text("""
                    select provider, status
                    from public.integration_connections
                    where org_id = :org_id
                """),
                {"org_id": org_id},
            )
        ).fetchall()

        for provider, status in rows:
            if provider in connected:
                connected[provider] = str(status).lower() in ("connected", "active", "ok")

    for provider in SUPPORTED:
        items.append({"provider": provider, "connected": connected[provider]})

    return {"items": items}


# ============================================================
# GREENHOUSE CONNECT
# ============================================================
@router.post("/connect/greenhouse")
async def connect_greenhouse(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if not await table_exists(db, "integration_connections"):
        raise HTTPException(
            status_code=503,
            detail="integration_connections table is not available yet. Run the integrations migration first.",
        )

    api_key = payload.get("api_key") or getattr(settings, "greenhouse_api_key", None)
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")

    secret = secrets.token_urlsafe(32)

    await upsert_connection_secret(
        db,
        actor.org_id,
        "greenhouse",
        secret,
        status="connected",
    )
    await upsert_connection_tokens(
        db,
        actor.org_id,
        "greenhouse",
        api_key,
        None,
        scopes=["harvest"],
    )
    await db.commit()

    try:
        client = await get_client()
        await client.start_workflow(
            IntegrationSyncWorkflow.run,
            actor.org_id,
            "greenhouse",
            secrets.token_urlsafe(12),
            id=f"sync-{actor.org_id}-greenhouse-initial",
            task_queue="foundry-people",
        )
    except Exception:
        # Do not fail the connect just because Temporal is down locally
        return {
            "ok": True,
            "provider": "greenhouse",
            "webhook_secret": secret,
            "sync_started": False,
        }

    return {
        "ok": True,
        "provider": "greenhouse",
        "webhook_secret": secret,
        "sync_started": True,
    }


# ============================================================
# LEVER CONNECT
# ============================================================
@router.post("/connect/lever")
async def connect_lever(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if not await table_exists(db, "integration_connections"):
        raise HTTPException(
            status_code=503,
            detail="integration_connections table is not available yet. Run the integrations migration first.",
        )

    state = secrets.token_urlsafe(24)
    auth_url = lever_build_auth_url(state)

    await upsert_connection_secret(
        db,
        actor.org_id,
        "lever",
        state,
        status="pending",
    )
    await db.commit()

    return {
        "ok": True,
        "provider": "lever",
        "oauth_url": auth_url,
    }


@router.get("/callback/lever")
async def callback_lever(
    code: str,
    state: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    conn = await get_connection(db, actor.org_id, "lever")
    if not conn or conn.get("webhook_secret") != state:
        raise HTTPException(status_code=400, detail="invalid_state")

    tokens = await lever_exchange_code(code)

    await upsert_connection_secret(
        db,
        actor.org_id,
        "lever",
        secrets.token_urlsafe(32),
        status="connected",
    )
    await upsert_connection_tokens(
        db,
        actor.org_id,
        "lever",
        tokens.get("access_token"),
        tokens.get("refresh_token"),
        scopes=tokens.get("scope", "").split() if isinstance(tokens.get("scope"), str) else [],
        external_account_id=tokens.get("account_id"),
    )
    await db.commit()

    try:
        client = await get_client()
        await client.start_workflow(
            IntegrationSyncWorkflow.run,
            actor.org_id,
            "lever",
            secrets.token_urlsafe(12),
            id=f"sync-{actor.org_id}-lever-initial",
            task_queue="foundry-people",
        )
    except Exception:
        return {"ok": True, "provider": "lever", "sync_started": False}

    return {"ok": True, "provider": "lever", "sync_started": True}


# ============================================================
# LINKEDIN CONNECT
# ============================================================
@router.post("/connect/linkedin")
async def connect_linkedin(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if not await table_exists(db, "integration_connections"):
        raise HTTPException(
            status_code=503,
            detail="integration_connections table is not available yet. Run the integrations migration first.",
        )

    client = LinkedInClient()
    auth_url, state = client.build_auth_url(actor.org_id)

    await upsert_connection_secret(
        db,
        actor.org_id,
        "linkedin",
        state,
        status="pending",
    )
    await db.commit()

    return {
        "ok": True,
        "provider": "linkedin",
        "oauth_url": auth_url,
    }


@router.get("/callback/linkedin")
async def callback_linkedin(
    code: str,
    state: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    conn = await get_connection(db, actor.org_id, "linkedin")
    if not conn or conn.get("webhook_secret") != state:
        raise HTTPException(status_code=400, detail="invalid_state")

    tokens = await LinkedInClient().exchange_code(code)

    await upsert_connection_secret(
        db,
        actor.org_id,
        "linkedin",
        secrets.token_urlsafe(32),
        status="connected",
    )
    await upsert_connection_tokens(
        db,
        actor.org_id,
        "linkedin",
        tokens.get("access_token"),
        tokens.get("refresh_token"),
        scopes=tokens.get("scopes", []),
        external_account_id=tokens.get("account_id"),
    )
    await db.commit()

    return {"ok": True, "provider": "linkedin"}


# ============================================================
# WEBHOOK HANDLER
# ============================================================
async def _handle_webhook(
    provider: str,
    org_id: str,
    request: Request,
    db: AsyncSession,
):
    if not await table_exists(db, "integration_connections"):
        raise HTTPException(
            status_code=503,
            detail="integration_connections table is not available yet. Run the integrations migration first.",
        )

    raw = await request.body()
    sig = request.headers.get("X-Webhook-Signature", "")

    conn = await get_connection(db, org_id, provider)
    secret = conn.get("webhook_secret") if conn else None

    if not secret or not verify_hmac_sha256(raw, secret, sig):
        raise HTTPException(status_code=401, detail="invalid_signature")

    payload = json.loads(raw.decode("utf-8") or "{}")
    event_type = payload.get("type") or payload.get("event")

    if await table_exists(db, "integration_events"):
        await db.execute(
            text("""
                insert into public.integration_events(
                    org_id,
                    provider,
                    event_type,
                    external_id,
                    payload,
                    created_at
                )
                values (
                    :org_id,
                    :provider,
                    :event_type,
                    :external_id,
                    cast(:payload as jsonb),
                    :created_at
                )
            """),
            {
                "org_id": org_id,
                "provider": provider,
                "event_type": event_type,
                "external_id": payload.get("id"),
                "payload": json.dumps(payload),
                "created_at": datetime.datetime.utcnow(),
            },
        )

    await db.commit()

    await route_event(db, org_id, provider, event_type, payload)

    try:
        client = await get_client()
        await client.start_workflow(
            IntegrationSyncWorkflow.run,
            org_id,
            provider,
            secrets.token_urlsafe(12),
            id=f"sync-{org_id}-{provider}-{secrets.token_urlsafe(6)}",
            task_queue="foundry-people",
        )
    except Exception:
        return {"ok": True, "sync_started": False}

    return {"ok": True, "sync_started": True}


@router.post("/webhook/greenhouse/{org_id}")
async def webhook_greenhouse(
    org_id: str,
    request: Request,
    db: AsyncSession = Depends(db_session),
):
    return await _handle_webhook("greenhouse", org_id, request, db)


@router.post("/webhook/lever/{org_id}")
async def webhook_lever(
    org_id: str,
    request: Request,
    db: AsyncSession = Depends(db_session),
):
    return await _handle_webhook("lever", org_id, request, db)


# ============================================================
# SALARY BENCHMARK
# ============================================================
@router.get("/salary/benchmark")
async def salary_benchmark(
    title: str,
    location: str,
    actor: Actor = Depends(require_org),
):
    client = SalaryDotComClient()
    return await client.get_salary_range(title, location)


# ============================================================
# REPLAY
# ============================================================
@router.post("/replay/{provider}")
async def replay(
    provider: str,
    actor: Actor = Depends(require_org),
):
    if provider not in SUPPORTED:
        raise HTTPException(status_code=400, detail="unsupported provider")

    try:
        client = await get_client()
        handle = await client.start_workflow(
            IntegrationReplayWorkflow.run,
            actor.org_id,
            provider,
            secrets.token_urlsafe(12),
            id=f"replay-{actor.org_id}-{provider}-{secrets.token_urlsafe(6)}",
            task_queue="foundry-people",
        )
        return {
            "ok": True,
            "provider": provider,
            "workflow_id": handle.id,
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal unavailable: {str(e)}",
        )
