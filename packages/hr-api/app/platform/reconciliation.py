from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import uuid
import pandas as pd

@dataclass
class ReconciliationFinding:
    finding_id: str
    ts: datetime
    severity: str
    message: str
    system_a: str
    system_b: str
    context: Dict

@dataclass
class Dispute:
    dispute_id: str
    opened_at: datetime
    status: str
    assigned_to: str
    description: str
    linked_findings: List[str]
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None

class ReconciliationEngine:
    """Compare Foundry vs other systems.

    For now, supports CSV uploads as stand-ins for payroll/ERP/legal.
    """

    def __init__(self) -> None:
        self._disputes: Dict[str, Dispute] = {}

    def open(self, description: str, assigned_to: str, linked_findings: List[str]) -> Dispute:
        d = Dispute(dispute_id=uuid.uuid4().hex, opened_at=datetime.utcnow(), status="open",
                   assigned_to=assigned_to, description=description, linked_findings=linked_findings)
        self._disputes[d.dispute_id] = d
        return d

    def resolve(self, dispute_id: str, resolution: str) -> Dispute:
        d = self._disputes[dispute_id]
        d.status = "resolved"
        d.resolution = resolution
        d.resolved_at = datetime.utcnow()
        return d

    def list(self) -> List[Dispute]:
        return list(self._disputes.values())
