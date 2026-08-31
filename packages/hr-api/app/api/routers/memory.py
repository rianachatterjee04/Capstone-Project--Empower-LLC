"""AI Company Memory router."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services.memory_service import (
    get_document,
    ingest_bulk,
    list_collections,
    list_documents,
    memory_summary,
    related,
    semantic_browse,
)


router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/summary")
async def summary(actor: Actor = Depends(require_org)):
    return memory_summary(actor.org_id)


@router.get("/collections")
async def collections(actor: Actor = Depends(require_org)):
    return {"items": list_collections(actor.org_id)}


@router.get("/documents")
async def documents(
    collection: str | None = None,
    q: str | None = None,
    actor: Actor = Depends(require_org),
):
    return {"items": list_documents(actor.org_id, collection=collection, q=q)}


@router.get("/documents/{doc_id}")
async def document(doc_id: str, actor: Actor = Depends(require_org)):
    out = get_document(actor.org_id, doc_id)
    if not out:
        raise HTTPException(status_code=404, detail="Document not found")
    return out


@router.get("/documents/{doc_id}/related")
async def related_docs(doc_id: str, actor: Actor = Depends(require_org)):
    return {"items": related(actor.org_id, doc_id)}


@router.post("/browse")
async def browse(payload: dict, actor: Actor = Depends(require_org)):
    return {
        "items": semantic_browse(
            actor.org_id,
            query=(payload.get("query") or "").strip(),
            collection=payload.get("collection"),
            top_k=int(payload.get("top_k") or 8),
        )
    }


@router.post("/ingest/bulk")
async def ingest(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items[] required")
    out = ingest_bulk(actor.org_id, items)
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="memory.bulk_ingest",
            entity_type="memory_collection",
            payload={"n_docs": len(out), "titles": [d["title"] for d in out][:10]},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return {"items": out}
