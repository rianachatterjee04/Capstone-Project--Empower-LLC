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
    def run_cap_table_recon(self, foundry: pd.DataFrame, external: pd.DataFrame, system_name: str) -> List[ReconciliationFinding]:
        findings: List[ReconciliationFinding] = []
        f = foundry.copy()
        e = external.copy()

        # Normalize
        for df in (f,e):
            if "Holder" in df.columns:
                df["Holder"] = df["Holder"].astype(str).str.strip()
            if "Shares" in df.columns:
                df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0)

        merged = f.merge(e, on="Holder", how="outer", suffixes=("_foundry", "_ext")).fillna(0.0)
        merged["delta"] = merged.get("Shares_foundry",0.0) - merged.get("Shares_ext",0.0)

        for _, row in merged.iterrows():
            if abs(row["delta"]) > 1e-6:
                findings.append(ReconciliationFinding(
                    finding_id=uuid.uuid4().hex,
                    ts=datetime.utcnow(),
                    severity="high" if abs(row["delta"]) > 1000 else "medium",
                    message=f"Share mismatch for {row['Holder']}: Foundry={row['Shares_foundry']}, {system_name}={row['Shares_ext']}",
                    system_a="foundry",
                    system_b=system_name,
                    context={"holder": row["Holder"], "delta": float(row["delta"])},
                ))
        return findings

class DisputeCenter:
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
