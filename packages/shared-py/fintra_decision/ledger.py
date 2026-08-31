"""Persistence seam for the decision ledger — kept PURE.

`fintra_decision` never imports a database. Instead a persistence backend
implements the tiny `LedgerSink` protocol (one method: `write(row)`), and
`persist_decision` shapes the append-only row, stamps a content-addressed
idempotency key, and writes it fail-soft. Each service binds its own concrete
sink at its boundary (the finance API binds a Supabase sink), so the contract
stays dependency-free and importable anywhere.

Idempotency is CONTENT-ADDRESSED: the key folds in the response's evidence_ref
(a hash of the decision). A retried, identical decision de-dupes to one row; a
genuine re-evaluation whose verdict/context changed produces a new evidence_ref,
hence a new key, hence a new ledger row — exactly what an audit trail wants.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from .contract import DecisionRequest, DecisionResponse


@runtime_checkable
class LedgerSink(Protocol):
    def write(self, row: Dict[str, Any]) -> None:
        """Persist one ledger row. May raise; persist_decision swallows it."""
        ...


def idempotency_key_for(request: DecisionRequest, response: DecisionResponse) -> str:
    """Deterministic, content-addressed key: same tenant + request + decision
    content => same key (retry-safe); changed decision => new key (new row)."""
    digest = (response.evidence_ref or "").split(":")[-1][:16] or "nohash"
    org = request.org_id or "none"
    return f"decision:{org}:{request.request_id}:{digest}"


def persist_decision(
    request: DecisionRequest,
    response: DecisionResponse,
    *,
    sink: LedgerSink,
) -> Optional[str]:
    """Fail-soft persist of a decision to the ledger. Returns the idempotency key
    regardless of sink outcome — a sink outage must NEVER affect the decision.
    Requires the response to be sealed (evidence_ref set); returns None otherwise."""
    if not response.evidence_ref:
        return None
    key = idempotency_key_for(request, response)
    row = response.to_ledger_row(request)
    row["idempotency_key"] = key
    try:
        sink.write(row)
    except Exception:
        pass  # sink outage must never break the decision path
    return key
