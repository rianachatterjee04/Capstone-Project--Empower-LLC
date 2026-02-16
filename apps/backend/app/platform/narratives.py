from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import uuid

@dataclass
class DecisionMemory:
    decision_id: str
    ts: datetime
    title: str
    context: str
    tradeoffs: str
    outcome: str
    author: str

class BoardNarratives:
    """Board-grade decision narratives + counterfactual framing."""
    def __init__(self) -> None:
        self._mem: List[DecisionMemory] = []

    def log(self, title: str, context: str, tradeoffs: str, outcome: str, author: str) -> DecisionMemory:
        d = DecisionMemory(uuid.uuid4().hex, datetime.utcnow(), title, context, tradeoffs, outcome, author)
        self._mem.append(d)
        return d

    def list(self) -> List[DecisionMemory]:
        return list(self._mem)

    def generate_quarter_story(self, metrics: Dict[str, float]) -> str:
        # Simple narrative template; can be upgraded with LLM.
        burn = metrics.get("equity_burn_pct", 0.0)
        dilution = metrics.get("dilution_ytd_pct", 0.0)
        runway = metrics.get("runway_months", 0.0)
        return (
            f"This quarter, equity burn was {burn:.2%} with YTD dilution at {dilution:.2%}. "
            f"Runway is estimated at {runway:.1f} months. "
            f"Key tradeoff: balancing hiring velocity with dilution control. "
            f"Next best actions: refresh policy review, option pool planning, and close freeze readiness."
        )
