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
        """Narrate the quarter from the metrics actually supplied.

        WHAT THIS USED TO DO
        It read `equity_burn_pct`, `dilution_ytd_pct` and `runway_months` --
        cap-table figures -- and the only caller passes none of them. Every
        board report therefore opened with "equity burn was 0.00% with YTD
        dilution at 0.00%. Runway is estimated at 0.0 months": three specific
        financial claims about a company, all fabricated from missing keys, on
        a report about headcount. Absent keys are now reported as absent, and
        the narrative describes the workforce metrics that were passed in.
        """
        known = {
            "annualized_payroll": ("annualized payroll", "${:,.0f}"),
            "performance_risk_cases": ("performance risk cases", "{:.0f}"),
            "market_comp_adjustments": ("market comp adjustments", "{:.0f}"),
            "headcount": ("headcount", "{:.0f}"),
        }
        stated = [
            label + " of " + fmt.format(metrics[key])
            for key, (label, fmt) in known.items()
            if metrics.get(key) is not None
        ]
        if not stated:
            return (
                "No workforce metrics were supplied for this quarter, so there "
                "is nothing to narrate. This is not a statement that the "
                "quarter was flat."
            )
        return (
            "This quarter's workforce position: " + "; ".join(stated) + ". "
            "Key tradeoff: balancing hiring velocity against compensation cost. "
            "Next best actions: policy review, compensation band refresh, and "
            "close-readiness for the next cycle."
        )
