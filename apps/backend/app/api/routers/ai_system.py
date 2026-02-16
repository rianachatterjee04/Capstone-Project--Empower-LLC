from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.services.ai_system_of_record import upsert_chunk, search_chunks, log_decision

router = APIRouter(prefix="/ai", tags=["ai"])

@router.post("/memory")
async def upsert_memory(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    namespace = payload.get("namespace","default")
    content = payload.get("content")
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    mid = await upsert_chunk(db, UUID(actor.org_id), namespace, content, payload.get("metadata") or {})
    await db.commit()
    return {"id": mid}

@router.post("/search")
async def search(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    namespace = payload.get("namespace","default")
    query = payload.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    k = int(payload.get("k", 8))
    rows = await search_chunks(db, UUID(actor.org_id), namespace, query, k=k)
    return {"results": rows}

@router.post("/decision")
async def decision(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    did = await log_decision(
        db=db,
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        decision_type=payload.get("decision_type","unknown"),
        entity_type=payload.get("entity_type"),
        entity_id=UUID(payload["entity_id"]) if payload.get("entity_id") else None,
        input_payload=payload.get("input") or {},
        output_payload=payload.get("output") or {},
        model=payload.get("model"),
    )
    await db.commit()
    return {"id": did}
