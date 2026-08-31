"""AI Helpdesk router — RAG-backed Q&A over policy + benefits documents."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services.rag_service import add_document, answer, list_documents


router = APIRouter(prefix="/ai-helpdesk", tags=["ai-helpdesk"])


@router.get("/documents")
async def documents(actor: Actor = Depends(require_org)):
    return {"items": list_documents(actor.org_id)}


@router.post("/documents")
async def upsert_document(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if not title or not body:
        raise HTTPException(status_code=400, detail="title and body required")
    out = add_document(
        org_id=actor.org_id,
        title=title,
        body=body,
        category=payload.get("category") or "policy",
        source=payload.get("source") or "internal",
    )
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai_helpdesk.document_added",
            entity_type="knowledge_doc",
            payload={"title": title, "category": payload.get("category")},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return out


@router.post("/ask")
async def ask(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question required")

    audience = payload.get("audience") or ("admin" if actor.role in ("owner", "admin", "hr") else "employee")
    result = answer(actor.org_id, question, audience=audience)

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai_helpdesk.ask",
            entity_type="ai_helpdesk",
            payload={
                "question": question[:500],
                "needs_escalation": result["needs_escalation"],
                "citations": [c["id"] for c in result.get("citations", [])],
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return result
