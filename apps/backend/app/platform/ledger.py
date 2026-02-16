from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json

from .models import LedgerEvent, new_event_id, Role

def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)

def _hash_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

class ImmutableLedger:
    """Append-only ledger for system-of-record status.

    - No deletes: corrections are superseding events.
    - Each event links to previous hash => tamper-evident chain.
    """

    def __init__(self) -> None:
        self._events: List[LedgerEvent] = []

    @property
    def events(self) -> List[LedgerEvent]:
        return list(self._events)

    def append(
        self,
        *,
        company_id: str,
        entity_id: str,
        event_type: str,
        actor: str,
        role: Role,
        payload: Dict[str, Any],
        ts: Optional[datetime] = None,
    ) -> LedgerEvent:
        ts = ts or datetime.utcnow()
        prev_hash = self._events[-1].hash if self._events else ""
        raw = {
            "event_id": new_event_id(),
            "ts": ts.isoformat(),
            "company_id": company_id,
            "entity_id": entity_id,
            "event_type": event_type,
            "actor": actor,
            "role": role,
            "payload": payload,
            "prev_hash": prev_hash,
        }
        h = _hash_str(_canonical(raw))
        ev = LedgerEvent(
            event_id=raw["event_id"],
            ts=ts,
            company_id=company_id,
            entity_id=entity_id,
            event_type=event_type,  # type: ignore
            actor=actor,
            role=role,
            payload=payload,
            prev_hash=prev_hash,
            hash=h,
        )
        self._events.append(ev)
        return ev

    def snapshot_hash(self) -> str:
        """Hash of the full chain."""
        return _hash_str(_canonical([e.hash for e in self._events]))

    def events_for_company(self, company_id: str) -> List[LedgerEvent]:
        return [e for e in self._events if e.company_id == company_id]

    def verify_chain(self) -> Tuple[bool, str]:
        prev = ""
        for i, e in enumerate(self._events):
            raw = {
                "event_id": e.event_id,
                "ts": e.ts.isoformat(),
                "company_id": e.company_id,
                "entity_id": e.entity_id,
                "event_type": e.event_type,
                "actor": e.actor,
                "role": e.role,
                "payload": e.payload,
                "prev_hash": e.prev_hash,
            }
            expected = _hash_str(_canonical(raw))
            if e.prev_hash != prev:
                return False, f"Broken prev_hash at index {i}"
            if e.hash != expected:
                return False, f"Tampered hash at index {i}"
            prev = e.hash
        return True, "ok"
