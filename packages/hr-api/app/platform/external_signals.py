from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

@dataclass
class MarketSignal:
    ts: datetime
    signal_type: str
    label: str
    value: float
    source: str
    context: Dict

class ExternalSignals:
    """Stub interface for external market signals.

    Students can later connect:
    - secondary market pricing (tender offers / private pricing)
    - compensation benchmarks by role/location
    - board/investor expectations by stage
    """

    def fetch_demo_signals(self, stage: str, industry: str) -> List[MarketSignal]:
        now = datetime.utcnow()
        # Demo numbers only; replace with connectors later.
        return [
            MarketSignal(now, "secondary_trend", "Secondary price index (demo)", 1.07, "demo", {"stage": stage, "industry": industry}),
            MarketSignal(now, "talent_pressure", "Talent market pressure (demo)", 0.62, "demo", {"region": "US"}),
            MarketSignal(now, "board_expectations", "Board hiring-plan tolerance (demo)", 0.18, "demo", {"stage": stage}),
        ]
