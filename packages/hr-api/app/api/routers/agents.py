"""Agent dispatch router."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services.agent_runtime import (
    AGENT_REGISTRY,
    list_agents,
    list_runs,
    run_agent,
)
from app.services.agent_marketplace_service import (
    categories as catalog_categories,
    install as catalog_install,
    list_catalog,
    uninstall as catalog_uninstall,
)


router = APIRouter(prefix="/agents", tags=["agents"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "manager")


@router.get("")
async def list_all(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": list_agents()}


@router.get("/runs")
async def runs(agent: str | None = None, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [r.to_dict() for r in list_runs(actor.org_id, agent)]}


@router.post("/{agent}/run")
async def trigger(
    agent: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    if agent not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown agent")
    run = await run_agent(agent, db, actor.org_id)
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type=f"agent.{agent}.run",
            entity_type="agent_run",
            payload={"summary": run.summary, "actions": len(run.actions), "confidence": run.confidence},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return run.to_dict()


@router.get("/catalog")
async def catalog(actor: Actor = Depends(require_org)):
    return {
        "items": list_catalog(actor.org_id),
        "categories": catalog_categories(),
    }


@router.post("/catalog/{agent_key}/install")
async def install_agent(
    agent_key: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = catalog_install(actor.org_id, agent_key)
    if not out:
        raise HTTPException(status_code=404, detail="Agent not found or not installable")
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="agent.installed",
            entity_type="agent_catalog",
            payload={"agent_key": agent_key},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return out


@router.post("/catalog/{agent_key}/uninstall")
async def uninstall_agent(
    agent_key: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    ok = catalog_uninstall(actor.org_id, agent_key)
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="agent.uninstalled",
            entity_type="agent_catalog",
            payload={"agent_key": agent_key, "ok": ok},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return {"ok": ok}


@router.post("/{agent}/approve-action/{action_id}")
async def approve_action(
    agent: str,
    action_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Record a human approval of an agent action.

    THIS DOES NOT EXECUTE THE ACTION. The execute path stays where it belongs
    (resume_ai, ai_interview, and so on) and is invoked from those surfaces.
    That is a defensible design — an approval endpoint that runs arbitrary
    agent actions is a different security question — but the response used to
    say only {"approved": true}, and the button was labelled "Approve" with no
    state change afterwards. Approving AI screening for four candidates left
    all four unscored, and the button still said Approve, so the natural next
    move is to press it again.

    The response now says what was recorded and what was not done.

    It also used to return {"approved": true} when the audit write had FAILED
    and been rolled back, because the except swallowed it. An approval is the
    human-in-the-loop gate; claiming to have recorded one that was never
    written is the last thing this endpoint should do.
    """
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type=f"agent.{agent}.action_approved",
            entity_type="agent_action",
            payload={"action_id": action_id},
        ))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail={
            "approved": False,
            "reason": "AUDIT_WRITE_FAILED",
            "message": ("The approval was not recorded, so it has not been "
                        "granted. Nothing was executed."),
            "error": str(exc)[:200],
        })
    return {
        "approved": True,
        "recorded": True,
        "agent": agent,
        "action_id": action_id,
        "executed": False,
        "next_step": ("Approval is recorded in the audit log. This action is "
                      "not executed automatically — run it from the surface it "
                      "belongs to."),
    }
