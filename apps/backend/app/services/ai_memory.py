from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.embeddings import mock_embedding

@dataclass
class MemoryItem:
    id: UUID
    namespace: str
    content: str
    metadata: Dict[str, Any]

async def upsert_memory(
    db: AsyncSession,
    org_id: UUID,
    namespace: str,
    content: str,
    metadata: Dict[str, Any] | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> UUID:
    """Insert a tenant-scoped memory row with embedding (pgvector)."""
    emb = mock_embedding(content)
    metadata = metadata or {}
    q = text("""
      insert into public.ai_memories(org_id, namespace, entity_type, entity_id, content, embedding, metadata)
      values (:org_id, :namespace, :entity_type, :entity_id, :content, :embedding::vector, :metadata::jsonb)
      returning id
    """)
    res = await db.execute(q, {
        "org_id": str(org_id),
        "namespace": namespace,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "content": content,
        "embedding": str(emb).replace("[","{").replace("]","}"),  # pgvector accepts array-ish literals; we cast to vector
        "metadata": json_dumps(metadata),
    })
    row = res.first()
    return row[0]

async def search_memory(
    db: AsyncSession,
    org_id: UUID,
    namespace: str,
    query_text: str,
    k: int = 5,
) -> List[MemoryItem]:
    """Vector search within a tenant+namespace."""
    emb = mock_embedding(query_text)
    q = text("""
      select id, namespace, content, metadata
      from public.ai_memories
      where org_id = :org_id and namespace = :namespace
      order by embedding <-> (:embedding::vector)
      limit :k
    """)
    res = await db.execute(q, {
        "org_id": str(org_id),
        "namespace": namespace,
        "embedding": str(emb).replace("[","{").replace("]","}"),
        "k": k,
    })
    out = []
    for r in res.fetchall():
        out.append(MemoryItem(id=r[0], namespace=r[1], content=r[2], metadata=r[3] or {}))
    return out

def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
