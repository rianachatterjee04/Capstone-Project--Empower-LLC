from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.api.schemas_enterprise import MemoryUpsert, MemorySearch, MemoryOut
from app.db.models import AuditEvent
from app.services.ai_memory import upsert_memory, search_memory

router = APIRouter(prefix="/ai/memory", tags=["ai"])


# ---------------------------------------------------------
# UPSERT MEMORY CHUNK (vector + lineage)
# ---------------------------------------------------------
@router.post("/upsert")
async def upsert(payload: MemoryUpsert, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    mid = await upsert_memory(
        db,
        org_id,
        payload.namespace,
        payload.content,
        payload.metadata,
        payload.entity_type,
        payload.entity_id
    )

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="ai_memory.upserted",
        entity_type="ai_memory",
        entity_id=mid,
        payload=payload.model_dump()
    ))

    await db.commit()
    return {"id": str(mid)}


# ---------------------------------------------------------
# SEMANTIC SEARCH
# ---------------------------------------------------------
@router.post("/search", response_model=list[MemoryOut])
async def search(payload: MemorySearch, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    items = await search_memory(db, org_id, payload.namespace, payload.query, payload.k)

    return [
        {"id": i.id, "namespace": i.namespace, "content": i.content, "metadata": i.metadata}
        for i in items
    ]


# ---------------------------------------------------------
# ENTITY MEMORY TIMELINE (legal reconstruction)
# ---------------------------------------------------------
@router.get("/entity/{entity_type}/{entity_id}")
async def entity_timeline(entity_type: str, entity_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    org_id = actor.org_id

    rows = (await db.execute(text("""
        select id, namespace, content, metadata, created_at
        from public.ai_memory_chunks
        where org_id=:org_id
        and entity_type=:etype
        and entity_id=:eid
        order by created_at asc
    """), {
        "org_id": org_id,
        "etype": entity_type,
        "eid": entity_id
    })).mappings().all()

    return {"timeline": [dict(r) for r in rows]}


# ---------------------------------------------------------
# AI DECISION RECORD (why system acted)
# ---------------------------------------------------------
@router.post("/decision")
async def record_decision(entity_type: str, entity_id: str, decision: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","system"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        insert into public.ai_decisions(org_id, entity_type, entity_id, decision_payload, actor_role)
        values (:org_id, :etype, :eid, :payload::jsonb, :role)
    """), {
        "org_id": actor.org_id,
        "etype": entity_type,
        "eid": entity_id,
        "payload": json.dumps(decision),
        "role": actor.role
    })

    await db.commit()
    return {"recorded": True}


# ---------------------------------------------------------
# HUMAN OVERRIDE (critical for legal defensibility)
# ---------------------------------------------------------
@router.post("/override")
async def override(entity_type: str, entity_id: str, reason: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        insert into public.ai_overrides(org_id, entity_type, entity_id, actor_user_id, reason)
        values (:org_id, :etype, :eid, :uid, :reason)
    """), {
        "org_id": actor.org_id,
        "etype": entity_type,
        "eid": entity_id,
        "uid": actor.user_id,
        "reason": reason
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="ai.override",
        entity_type=entity_type,
        entity_id=UUID(entity_id),
        payload={"reason": reason}
    ))

    await db.commit()
    return {"override_recorded": True}

