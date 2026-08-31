"""Executive AI Copilot router."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services.exec_copilot_service import answer


router = APIRouter(prefix="/exec-copilot", tags=["exec-copilot"])


@router.post("/ask")
async def ask(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question required")
    out = await answer(db, actor.org_id, question)
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="exec_copilot.ask",
            entity_type="exec_copilot",
            payload={"question": question[:500], "facts": out.get("facts", {})},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return out
