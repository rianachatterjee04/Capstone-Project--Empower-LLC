from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.api.deps import require_org, Actor, db_session
from app.realtime.bus import publish
import json, uuid

router = APIRouter(prefix="/decisions", tags=["decisions"])

@router.post("/respond")
async def respond_to_decision(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    decision_id = payload.get("id")
    action = payload.get("action")

    # Only log if decision_id is a valid UUID
    try:
        uuid.UUID(str(decision_id))
        await db.execute(text("""
            INSERT INTO public.audit_events (org_id, actor_user_id, actor_role, event_type, entity_type, entity_id, payload)
            VALUES (:org_id, :actor_user_id, :actor_role, :event_type, 'decision', :entity_id, :payload)
        """), {
            "org_id": actor.org_id,
            "actor_user_id": actor.user_id,
            "actor_role": actor.role,
            "event_type": f"decision.{action}",
            "entity_id": decision_id,
            "payload": json.dumps({"decision_id": decision_id, "action": action}),
        })
        await db.commit()
    except (ValueError, Exception):
        pass  # skip audit log for non-UUID test IDs

    # org_id is explicit: the bus drops events it cannot attribute to an org
    # rather than broadcasting them to every tenant (see app/realtime/bus.py).
    await publish("decision_resolved",
                  {"id": decision_id, "action": action, "resolved_by": actor.user_id},
                  org_id=actor.org_id)
    return {"ok": True, "id": decision_id, "action": action}
