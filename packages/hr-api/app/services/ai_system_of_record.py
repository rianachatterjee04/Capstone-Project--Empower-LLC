from __future__ import annotations
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

from app.services.embeddings_provider import embed

async def upsert_chunk(db: AsyncSession, org_id: UUID, namespace: str, content: str, metadata: Dict[str, Any]) -> str:
    vec = embed(content)
    res = await db.execute(text("""
        insert into public.ai_memory_chunks(org_id, namespace, content, metadata, embedding)
        values (:org_id, :namespace, :content, cast(:metadata as jsonb), :embedding)
        returning id
    """), {
        "org_id": str(org_id),
        "namespace": namespace,
        "content": content,
        "metadata": json.dumps(metadata or {}),
        "embedding": vec,
    })
    return str(res.first()[0])

async def search_chunks(db: AsyncSession, org_id: UUID, namespace: str, query: str, k: int = 8) -> List[Dict[str, Any]]:
    qvec = embed(query)
    res = await db.execute(text("""
        select id, content, metadata, 1 - (embedding <=> :qvec) as score
        from public.ai_memory_chunks
        where org_id = :org_id and namespace = :namespace and embedding is not null
        order by embedding <=> :qvec
        limit :k
    """), {"org_id": str(org_id), "namespace": namespace, "qvec": qvec, "k": k})
    rows = []
    for r in res.fetchall():
        rows.append({"id": str(r[0]), "content": r[1], "metadata": r[2], "score": float(r[3])})
    return rows

async def log_decision(db: AsyncSession, org_id: UUID, actor_user_id: Optional[UUID], actor_role: Optional[str],
                       decision_type: str, entity_type: Optional[str], entity_id: Optional[UUID],
                       input_payload: Dict[str, Any], output_payload: Dict[str, Any], model: Optional[str]) -> str:
    res = await db.execute(text("""
        insert into public.ai_decisions(org_id, actor_user_id, actor_role, decision_type, entity_type, entity_id, input, output, model)
        values (:org_id, :actor_user_id, :actor_role, :decision_type, :entity_type, :entity_id, cast(:input as jsonb), cast(:output as jsonb), :model)
        returning id
    """), {
        "org_id": str(org_id),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "actor_role": actor_role,
        "decision_type": decision_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "input": json.dumps(input_payload or {}),
        "output": json.dumps(output_payload or {}),
        "model": model,
    })
    return str(res.first()[0])
