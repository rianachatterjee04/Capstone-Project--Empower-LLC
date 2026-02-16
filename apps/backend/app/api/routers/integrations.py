from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import secrets, json, datetime

from app.api.deps import require_org, db_session, Actor
from app.integrations.store import upsert_connection_secret, upsert_connection_tokens, get_connection
from app.integrations.common import verify_hmac_sha256
from app.core.config import settings

# Providers
from app.integrations.lever_oauth import build_auth_url, exchange_code
from app.integrations.linkedin import LinkedInClient
from app.integrations.salary_dot_com import SalaryDotComClient

# Temporal
from app.temporal.client import get_client
from app.temporal.workflows.sync import IntegrationSyncWorkflow
from app.temporal.workflows.replay import IntegrationReplayWorkflow

# NEW: internal orchestration
from app.workflow.engine import engine

router = APIRouter(prefix="/integrations", tags=["integrations"])

SUPPORTED = ["greenhouse", "lever", "linkedin", "salarydotcom"]


# ============================================================
# EVENT ROUTING (THE MISSING ENTERPRISE PIECE)
# ============================================================
async def route_event(db: AsyncSession, org_id: str, provider: str, event_type: str, payload: dict):
    """
    Converts external ATS events → internal HR workflows
    This is what makes the system replace Greenhouse instead of depend on it
    """

    # Candidate hired → create employee + onboarding
    if event_type in ("candidate.hired", "hire", "application_hired"):
        engine.trigger("employee.hired", {
            "org_id": org_id,
            "provider": provider,
            "payload": payload
        })

    # Candidate rejected → audit defense record
    if event_type in ("candidate.rejected", "application_rejected"):
        engine.trigger("candidate.rejected", {
            "org_id": org_id,
            "payload": payload
        })

    # Offer created → approval workflow
    if event_type in ("offer.created", "offer_opened"):
        engine.trigger("offer.created", {
            "org_id": org_id,
            "payload": payload
        })

    # Job opened → workforce planning update
    if event_type in ("job.created", "opening.created"):
        engine.trigger("headcount.plan.changed", {
            "org_id": org_id
        })

    # Always run reconciliation (prevents silent drift)
    engine.trigger("integration.sync.completed", {
        "org_id": org_id,
        "provider": provider
    })


# ============================================================
# PROVIDERS
# ============================================================
@router.get("/providers")
async def providers(actor: Actor = Depends(require_org)):
    return {"providers": SUPPORTED}


# ============================================================
# GREENHOUSE CONNECT
# ============================================================
@router.post("/connect/greenhouse")
async def connect_greenhouse(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    api_key = payload.get("api_key") or settings.greenhouse_api_key
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")

    secret = secrets.token_urlsafe(32)

    await upsert_connection_secret(db, actor.org_id, "greenhouse", secret, status="connected")
    await upsert_connection_tokens(db, actor.org_id, "greenhouse", api_key, None, scopes=["harvest"])
    await db.commit()

    client = await get_client()
    await client.start_workflow(
        IntegrationSyncWorkflow.run,
        actor.org_id, "greenhouse", secrets.token_urlsafe(12),
        id=f"sync-{actor.org_id}-greenhouse-initial",
        task_queue="foundry-people",
    )

    return {"ok": True, "provider": "greenhouse", "webhook_secret": secret}


# ============================================================
# LINKEDIN
# ============================================================
@router.post("/connect/linkedin")
async def connect_linkedin(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    client = LinkedInClient()
    url, state = client.build_auth_url(actor.org_id)

    await upsert_connection_secret(db, actor.org_id, "linkedin", state, status="pending")
    await db.commit()

    return {"oauth_url": url}


@router.get("/callback/linkedin")
async def callback_linkedin(code: str, state: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    conn = await get_connection(db, actor.org_id, "linkedin")
    if not conn or conn.get("webhook_secret") != state:
        raise HTTPException(status_code=400, detail="invalid_state")

    tokens = await LinkedInClient().exchange_code(code)

    await upsert_connection_secret(db, actor.org_id, "linkedin", secrets.token_urlsafe(32), status="connected")
    await upsert_connection_tokens(db, actor.org_id, "linkedin", tokens["access_token"], tokens.get("refresh_token"))
    await db.commit()

    return {"ok": True}


# ============================================================
# WEBHOOK HANDLER (UPGRADED)
# ============================================================
async def _handle_webhook(provider: str, org_id: str, request: Request, db: AsyncSession):

    raw = await request.body()
    sig = request.headers.get("X-Webhook-Signature", "")

    conn = await get_connection(db, org_id, provider)
    secret = conn.get("webhook_secret") if conn else None

    if not secret or not verify_hmac_sha256(raw, secret, sig):
        raise HTTPException(status_code=401, detail="invalid_signature")

    payload = json.loads(raw.decode("utf-8") or "{}")
    event_type = payload.get("type") or payload.get("event")

    # store immutable audit record
    await db.execute(text("""
        insert into public.integration_events(org_id,provider,event_type,external_id,payload,created_at)
        values (:org_id,:provider,:event_type,:external_id,:payload::jsonb,:now)
    """), {
        "org_id": org_id,
        "provider": provider,
        "event_type": event_type,
        "external_id": payload.get("id"),
        "payload": json.dumps(payload),
        "now": datetime.datetime.utcnow()
    })

    await db.commit()

    # NEW: route to HR workflows
    await route_event(db, org_id, provider, event_type, payload)

    # async sync
    client = await get_client()
    await client.start_workflow(
        IntegrationSyncWorkflow.run,
        org_id, provider, secrets.token_urlsafe(12),
        id=f"sync-{org_id}-{provider}-{secrets.token_urlsafe(6)}",
        task_queue="foundry-people",
    )

    return {"ok": True}


@router.post("/webhook/greenhouse/{org_id}")
async def webhook_greenhouse(org_id: str, request: Request, db: AsyncSession = Depends(db_session)):
    return await _handle_webhook("greenhouse", org_id, request, db)


@router.post("/webhook/lever/{org_id}")
async def webhook_lever(org_id: str, request: Request, db: AsyncSession = Depends(db_session)):
    return await _handle_webhook("lever", org_id, request, db)


# ============================================================
# SALARY BENCHMARK
# ============================================================
@router.get("/salary/benchmark")
async def salary_benchmark(title: str, location: str, actor: Actor = Depends(require_org)):
    return await SalaryDotComClient().get_salary_range(title, location)


# ============================================================
# REPLAY
# ============================================================
@router.post("/replay/{provider}")
async def replay(provider: str, actor: Actor = Depends(require_org)):

    if provider not in SUPPORTED:
        raise HTTPException(status_code=400, detail="unsupported provider")

    client = await get_client()
    handle = await client.start_workflow(
        IntegrationReplayWorkflow.run,
        actor.org_id, provider, secrets.token_urlsafe(12),
        id=f"replay-{actor.org_id}-{provider}-{secrets.token_urlsafe(6)}",
        task_queue="foundry-people",
    )

    return {"workflow_id": handle.id}

