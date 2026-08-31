from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
import uuid
import numpy as np
import pandas as pd

@dataclass
class TrustAlert:
    alert_id: str
    ts: datetime
    severity: str
    message: str
    context: Dict

class TrustLayer:
    """Employee psychology & trust layer.

    - Comprehension score (proxy) from onboarding quiz + chatbot interactions
    - Perceived fairness index (proxy) from grant distribution variance
    - Trust decay alerts when equity loses motivational effect
    """

    def equity_comprehension_score(self, quiz_results: pd.DataFrame) -> float:
        if quiz_results is None or quiz_results.empty:
            return 0.5
        score = quiz_results.get("score", pd.Series([0.5]*len(quiz_results))).mean()
        return float(np.clip(score, 0.0, 1.0))

    def perceived_fairness_index(self, grants: pd.DataFrame, group_field: str = "Department") -> float:
        if grants is None or grants.empty or group_field not in grants.columns or "Shares" not in grants.columns:
            return 0.5
        g = grants.copy()
        g["Shares"] = pd.to_numeric(g["Shares"], errors="coerce").fillna(0.0)
        by = g.groupby(group_field)["Shares"].mean()
        if len(by) <= 1:
            return 0.75
        cv = float(by.std() / (by.mean() + 1e-9))
        # lower CV => more fairness, map to 0..1
        fairness = float(np.clip(1.0 - cv, 0.0, 1.0))
        return fairness

    def trust_decay_alerts(self, comprehension: float, fairness: float) -> List[TrustAlert]:
        alerts: List[TrustAlert] = []
        now = datetime.utcnow()
        if comprehension < 0.35:
            alerts.append(TrustAlert(uuid.uuid4().hex, now, "high", "Equity comprehension is low. Add education nudges & personalized explainers.", {"score": comprehension}))
        if fairness < 0.45:
            alerts.append(TrustAlert(uuid.uuid4().hex, now, "medium", "Perceived fairness risk. Review grant distribution & refresh strategy.", {"fairness": fairness}))
        return alerts
