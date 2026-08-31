from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid

Role = Literal["cfo", "hr", "legal", "board", "employee", "investor", "auditor", "admin"]


GrantType = Literal["ISO", "NSO", "RSU", "Warrant", "EMI"]

EventType = Literal[
    "GRANT_ISSUED",
    "GRANT_ACCEPTED",
    "EXERCISE_EVENT",
    "CANCEL_EVENT",
    "POLICY_VERSION_PUBLISHED",
    "BOARD_APPROVAL",
    "CLOSE_FREEZE",
    "RECONCILIATION_RUN",
    "DISPUTE_OPENED",
    "DISPUTE_RESOLVED",
]

@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    ts: datetime
    entity_id: str
    company_id: str
    event_type: EventType
    actor: str
    role: Role
    payload: Dict[str, Any]
    prev_hash: str = ""
    hash: str = ""

def new_event_id() -> str:
    return uuid.uuid4().hex
