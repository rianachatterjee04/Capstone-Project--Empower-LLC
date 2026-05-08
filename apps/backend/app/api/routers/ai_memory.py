from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.api.schemas_enterprise import MemoryUpsert, MemorySearch, MemoryOut
from app.core.json_utils import json_safe
from app.db.models import AuditEvent
from app.services.ai_memory import upsert_memory, search_memory
from app.services.embeddings_provider import EmbeddingError

router = APIRouter(prefix="/ai/memory", tags=["ai"])


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


# ---------------------------------------------------------
# UPSERT MEMORY CHUNK
# ---------------------------------------------------------
@router.post("/upsert")
async def upsert(
    payload: MemoryUpsert,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)

    if org_id is None or user_id is None:
        raise HTTPException(status_code=400, detail="Missing actor identifiers")

    if not await table_exists(db, "ai_memories"):
        raise HTTPException(
            status_code=503,
            detail="ai_memories table is not available yet. Run the AI memory migration first.",
        )

    try:
        mid = await upsert_memory(
            db=db,
            org_id=org_id,
            namespace=payload.namespace,
            content=payload.content,
            metadata=payload.metadata,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{exc}. Set EMBEDDINGS_PROVIDER=mock for local dev or configure OPENAI_API_KEY.",
        ) from exc

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="ai_memory.upserted",
            entity_type="ai_memory",
            entity_id=mid,
            payload=json_safe(payload.model_dump()),
        )
    )

    await db.commit()
    return {"id": str(mid)}


# ---------------------------------------------------------
# SEMANTIC SEARCH
# ---------------------------------------------------------
@router.post("/search", response_model=list[MemoryOut])
async def search(
    payload: MemorySearch,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "ai_memories"):
        return []

    try:
        items = await search_memory(
            db=db,
            org_id=org_id,
            namespace=payload.namespace,
            query_text=payload.query,
            k=payload.k,
        )
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{exc}. Set EMBEDDINGS_PROVIDER=mock for local dev or configure OPENAI_API_KEY.",
        ) from exc

    return [
        MemoryOut(
            id=i.id,
            namespace=i.namespace,
            content=i.content,
            metadata=i.metadata or {},
        )
        for i in items
    ]


# ---------------------------------------------------------
# ENTITY MEMORY TIMELINE
# ---------------------------------------------------------
@router.get("/entity/{entity_type}/{entity_id}")
async def entity_timeline(
    entity_type: str,
    entity_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "ai_memories"):
        return {"timeline": []}

    rows = (
        await db.execute(
            text("""
                select id, namespace, content, metadata, entity_type, entity_id
                from public.ai_memories
                where org_id = :org_id
                  and entity_type = :etype
                  and entity_id = :eid
                order by id asc
            """),
            {
                "org_id": org_id,
                "etype": entity_type,
                "eid": entity_id,
            },
        )
    ).mappings().all()

    return {"timeline": [dict(r) for r in rows]}


# ---------------------------------------------------------
# AI DECISION RECORD
# ---------------------------------------------------------
@router.post("/decision")
async def record_decision(
    entity_type: str,
    entity_id: str,
    decision: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "system"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "ai_decisions"):
        raise HTTPException(
            status_code=503,
            detail="ai_decisions table is not available yet. Run the AI memory migration first.",
        )

    await db.execute(
        text("""
            insert into public.ai_decisions(
                org_id,
                entity_type,
                entity_id,
                decision_payload,
                actor_role
            )
            values (
                :org_id,
                :etype,
                :eid,
                cast(:payload as jsonb),
                :role
            )
        """),
        {
            "org_id": org_id,
            "etype": entity_type,
            "eid": entity_id,
            "payload": json.dumps(json_safe(decision)),
            "role": actor.role,
        },
    )

    await db.commit()
    return {"recorded": True}


# ---------------------------------------------------------
# HUMAN OVERRIDE
# ---------------------------------------------------------
@router.post("/override")
async def override(
    entity_type: str,
    entity_id: str,
    reason: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)

    if org_id is None or user_id is None:
        raise HTTPException(status_code=400, detail="Missing actor identifiers")

    if not await table_exists(db, "ai_overrides"):
        raise HTTPException(
            status_code=503,
            detail="ai_overrides table is not available yet. Run the AI memory migration first.",
        )

    await db.execute(
        text("""
            insert into public.ai_overrides(
                org_id,
                entity_type,
                entity_id,
                actor_user_id,
                reason
            )
            values (
                :org_id,
                :etype,
                :eid,
                :uid,
                :reason
            )
        """),
        {
            "org_id": org_id,
            "etype": entity_type,
            "eid": entity_id,
            "uid": user_id,
            "reason": reason,
        },
    )

    audit_entity_id = None
    try:
        audit_entity_id = UUID(str(entity_id))
    except Exception:
        audit_entity_id = None

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="ai.override",
            entity_type=entity_type,
            entity_id=audit_entity_id,
            payload={"reason": reason},
        )
    )

    await db.commit()
    return {"override_recorded": True}
