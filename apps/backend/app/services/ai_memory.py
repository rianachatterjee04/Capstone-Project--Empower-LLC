from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings import mock_embedding


@dataclass
class MemoryItem:
    id: UUID
    namespace: str
    content: str
    metadata: Dict[str, Any]


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"


async def upsert_memory(
    db: AsyncSession,
    org_id: UUID,
    namespace: str,
    content: str,
    metadata: Dict[str, Any] | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> UUID:
    emb = mock_embedding(content)
    metadata = metadata or {}

    q = text("""
        insert into public.ai_memories(
            org_id,
            namespace,
            entity_type,
            entity_id,
            content,
            embedding,
            metadata
        )
        values (
            :org_id,
            :namespace,
            :entity_type,
            :entity_id,
            :content,
            cast(:embedding as vector),
            cast(:metadata as jsonb)
        )
        returning id
    """)

    res = await db.execute(
        q,
        {
            "org_id": org_id,
            "namespace": namespace,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "content": content,
            "embedding": vector_literal(emb),
            "metadata": json_dumps(metadata),
        },
    )

    row = res.first()
    if not row:
        raise RuntimeError("Failed to insert AI memory row")

    return row[0]


async def search_memory(
    db: AsyncSession,
    org_id: UUID,
    namespace: str,
    query_text: str,
    k: int = 5,
) -> List[MemoryItem]:
    emb = mock_embedding(query_text)

    q = text("""
        select id, namespace, content, metadata
        from public.ai_memories
        where org_id = :org_id
          and namespace = :namespace
        order by embedding <-> cast(:embedding as vector)
        limit :k
    """)

    res = await db.execute(
        q,
        {
            "org_id": org_id,
            "namespace": namespace,
            "embedding": vector_literal(emb),
            "k": k,
        },
    )

    out: List[MemoryItem] = []
    for r in res.fetchall():
        out.append(
            MemoryItem(
                id=r[0],
                namespace=r[1],
                content=r[2],
                metadata=r[3] or {},
            )
        )
    return out
