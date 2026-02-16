from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class OrgContext:
    org_id: str
    employee: Optional[Dict] = None
    manager: Optional[Dict] = None
    team: Optional[list] = None
    history: Optional[list] = None
    compensation: Optional[Dict] = None
    performance: Optional[Dict] = None
    risk_scores: Optional[Dict] = None


@dataclass
class OrgDecision:
    action: str
    confidence: float
    reasoning: str
    metadata: Dict[str, Any]

