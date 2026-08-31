from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class OrgContext:
    org_id: str
    event: Optional[str] = None
    payload: Optional[Dict] = None
    employee: Optional[Dict] = None
    manager: Optional[Dict] = None
    team: Optional[list] = None
    history: Optional[list] = None
    org_snapshot: Optional[Dict] = None
    open_cases: Optional[list] = None
    reviews: Optional[list] = None
    compensation: Optional[Dict] = None
    performance: Optional[Dict] = None
    risk_scores: Optional[Dict] = None
    # aliases expected by simulator.py
    employees: Optional[list] = None
    cases: Optional[list] = None


@dataclass
class OrgDecision:
    action: str
    confidence: float
    reasoning: str
    metadata: Dict[str, Any]