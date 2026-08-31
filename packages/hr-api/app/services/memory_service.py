"""AI Company Memory.

A richer Notion-style knowledge layer built on top of the existing RAG store.
This service:
  - groups documents into collections (policies, benefits, onboarding, …)
  - supports multi-doc bulk ingestion
  - exposes semantic browse (rank docs by relevance for a query)
  - returns "related documents" for any source doc
  - tracks lightweight metadata (tags, last updated, source)

The rag_service is the underlying storage; this module is the "knowledge"
projection of it. New collections seed automatically the first time an org
hits the endpoint.
"""
from __future__ import annotations

import math
import textwrap
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services.embeddings import embedding
from app.services.rag_service import (
    KnowledgeDoc,
    _ensure_seeded as _ensure_rag_seeded,  # type: ignore
    _cosine,                                # type: ignore
)


# ---------------------------------------------------------------------------
@dataclass
class MemoryMeta:
    tags: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    owner: Optional[str] = None
    source_label: Optional[str] = None


_meta_lock = threading.RLock()
# Org-scoped metadata layered on top of rag_service KnowledgeDoc store.
_meta: dict[str, dict[str, MemoryMeta]] = {}


# ---------------------------------------------------------------------------
# Additional seed docs that give the Memory page real substance out of the
# box. Inserted lazily once per org if they're not present.
# ---------------------------------------------------------------------------
_EXTRA_SEED: list[KnowledgeDoc] = [
    KnowledgeDoc(
        id="comp-philosophy",
        title="Compensation Philosophy",
        category="compensation",
        body=(
            "We pay at or above the 50th percentile for our role bands and adjust "
            "annually based on market data. Promotions are tied to scope and "
            "consistent above-bar performance — not tenure. Comp letters always "
            "include band, compa-ratio, and rationale so the conversation is "
            "transparent. Equity awards refresh after the 4th year for top "
            "performers."
        ),
        source="internal",
    ),
    KnowledgeDoc(
        id="performance-philosophy",
        title="Performance Philosophy",
        category="performance",
        body=(
            "Performance is a conversation, not a paperwork exercise. We run "
            "structured cycles each quarter: self → peer → manager → calibration "
            "→ approval → delivery. Vague or biased language is flagged before "
            "delivery. Ratings inform development and comp, never punish."
        ),
        source="internal",
    ),
    KnowledgeDoc(
        id="learning-program",
        title="Learning & Development Program",
        category="learning",
        body=(
            "Every employee has a learning plan tied to their role's skill "
            "profile and their personal growth goals. We fund $1,500/yr per "
            "person for external courses, and an additional $500 for "
            "conferences. Required compliance trainings refresh annually."
        ),
        source="internal",
    ),
    KnowledgeDoc(
        id="manager-playbook",
        title="Manager Playbook",
        category="manager",
        body=(
            "Run weekly 1:1s; capture decisions in your notes doc. Use the "
            "balanced-feedback rewriter before sending written feedback. Open a "
            "stay interview when the workforce risk engine flags someone in your "
            "team. Comp conversations happen in dedicated 1:1s — never end-of-quarter."
        ),
        source="internal",
    ),
    KnowledgeDoc(
        id="equipment-request",
        title="How to request equipment",
        category="ops",
        body=(
            "All standard equipment requests (laptop, monitor, keyboard) are "
            "approved by IT through the in-app workflow. Non-standard requests "
            "(specialty peripherals, dual monitors above 32\") require manager "
            "approval. Ship-to-home and ship-to-office options are both supported."
        ),
        source="internal",
    ),
    KnowledgeDoc(
        id="sales-onboarding",
        title="Sales Onboarding Summary",
        category="onboarding",
        body=(
            "Week 1: shadow 5 customer calls with veteran AEs. Week 2: complete "
            "product certification + ICP deep-dive. Week 3: run your first "
            "discovery call with a buddy on the line. Week 4: own your pipeline "
            "with weekly forecast reviews. Ramp expectation: 25% quota by month "
            "3, full quota by month 5."
        ),
        source="internal",
    ),
    KnowledgeDoc(
        id="career-paths",
        title="Career Paths & Promotion Criteria",
        category="career",
        body=(
            "Each role ladder publishes promotion criteria. ICs grow through "
            "scope and impact; managers grow through team outcomes and hiring "
            "quality. There is no minimum tenure — see the skills graph for the "
            "exact gap to your next role."
        ),
        source="internal",
    ),
]


def _ensure_extra(org_id: str) -> list[KnowledgeDoc]:
    docs = _ensure_rag_seeded(org_id)
    existing_ids = {d.id for d in docs}
    added: list[KnowledgeDoc] = []
    for d in _EXTRA_SEED:
        if d.id in existing_ids:
            continue
        try:
            emb = embedding(d.body)
        except Exception:
            emb = []
        copy = KnowledgeDoc(**{**d.__dict__, "embedding": emb})
        docs.append(copy)
        added.append(copy)
    if added:
        _ensure_meta(org_id)
        for d in added:
            _meta[org_id].setdefault(d.id, MemoryMeta(tags=[d.category], source_label=d.source))
    return docs


def _ensure_meta(org_id: str) -> None:
    with _meta_lock:
        if org_id not in _meta:
            _meta[org_id] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_count(body: str) -> int:
    """Rough reading-time estimator (words ~ 200 wpm)."""
    words = len(body.split())
    return max(1, round(words / 200))


def _doc_to_dict(d: KnowledgeDoc, meta: Optional[MemoryMeta] = None) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "category": d.category,
        "source": d.source,
        "preview": d.body[:240] + ("…" if len(d.body) > 240 else ""),
        "body": d.body,
        "tags": list(meta.tags) if meta else [d.category],
        "updated_at": meta.updated_at if meta else None,
        "owner": meta.owner if meta else None,
        "source_label": meta.source_label if meta else d.source,
        "read_minutes": _read_count(d.body),
        "char_count": len(d.body),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def list_collections(org_id: str) -> list[dict]:
    docs = _ensure_extra(org_id)
    counts: dict[str, int] = {}
    for d in docs:
        counts[d.category] = counts.get(d.category, 0) + 1
    return [
        {"id": cat, "label": cat.replace("_", " ").title(), "count": n}
        for cat, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def list_documents(org_id: str, *, collection: Optional[str] = None, q: Optional[str] = None) -> list[dict]:
    docs = _ensure_extra(org_id)
    _ensure_meta(org_id)
    meta = _meta[org_id]
    rows: list[dict] = []
    for d in docs:
        if collection and d.category != collection:
            continue
        if q:
            ql = q.lower()
            if ql not in d.title.lower() and ql not in d.body.lower():
                continue
        rows.append(_doc_to_dict(d, meta.get(d.id)))
    return rows


def get_document(org_id: str, doc_id: str) -> Optional[dict]:
    docs = _ensure_extra(org_id)
    _ensure_meta(org_id)
    meta = _meta[org_id]
    for d in docs:
        if d.id == doc_id:
            return _doc_to_dict(d, meta.get(d.id))
    return None


def related(org_id: str, doc_id: str, top_k: int = 4) -> list[dict]:
    docs = _ensure_extra(org_id)
    _ensure_meta(org_id)
    target = next((d for d in docs if d.id == doc_id), None)
    if not target or not target.embedding:
        return []
    scored: list[tuple[float, KnowledgeDoc]] = []
    for d in docs:
        if d.id == doc_id or not d.embedding:
            continue
        sem = _cosine(target.embedding, d.embedding)
        # tiny boost when categories match
        if d.category == target.category:
            sem += 0.05
        scored.append((sem, d))
    scored.sort(key=lambda kv: kv[0], reverse=True)
    out = [_doc_to_dict(d, _meta[org_id].get(d.id)) for _, d in scored[:top_k]]
    return out


def semantic_browse(org_id: str, query: str, *, collection: Optional[str] = None, top_k: int = 8) -> list[dict]:
    docs = _ensure_extra(org_id)
    _ensure_meta(org_id)
    if not query:
        return list_documents(org_id, collection=collection)[:top_k]
    try:
        qv = embedding(query)
    except Exception:
        qv = []
    scored: list[tuple[float, KnowledgeDoc]] = []
    qlow = query.lower()
    for d in docs:
        if collection and d.category != collection:
            continue
        sem = _cosine(qv, d.embedding) if qv and d.embedding else 0.0
        kw = sum(1 for tok in qlow.split() if tok in d.body.lower()) / max(len(qlow.split()), 1)
        title_hit = 0.4 if qlow in d.title.lower() else 0.0
        score = 0.6 * sem + 0.3 * kw + title_hit
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [_doc_to_dict(d, _meta[org_id].get(d.id)) for _, d in scored[:top_k]]


def ingest_bulk(org_id: str, items: list[dict]) -> list[dict]:
    docs = _ensure_extra(org_id)
    _ensure_meta(org_id)
    out: list[dict] = []
    for item in items:
        title = (item.get("title") or "Untitled").strip()
        body = (item.get("body") or "").strip()
        if not body:
            continue
        category = (item.get("category") or "policy").strip()
        source = (item.get("source") or "internal").strip()
        owner = item.get("owner")
        tags = list(item.get("tags") or [])
        try:
            emb = embedding(body)
        except Exception:
            emb = []
        doc = KnowledgeDoc(
            id=f"doc-{uuid.uuid4().hex[:8]}",
            title=title,
            category=category,
            body=body,
            embedding=emb,
            source=source,
        )
        docs.append(doc)
        _meta[org_id][doc.id] = MemoryMeta(
            tags=tags or [category],
            owner=owner,
            source_label=source,
        )
        out.append(_doc_to_dict(doc, _meta[org_id][doc.id]))
    return out


def memory_summary(org_id: str) -> dict:
    docs = _ensure_extra(org_id)
    chars = sum(len(d.body) for d in docs)
    by_cat: dict[str, int] = {}
    for d in docs:
        by_cat[d.category] = by_cat.get(d.category, 0) + 1
    return {
        "total_documents": len(docs),
        "collections": len(by_cat),
        "total_words": sum(len(d.body.split()) for d in docs),
        "char_count": chars,
        "by_collection": by_cat,
    }
