"""Predictive attrition / flight-risk scaffolding.

Heuristic scoring intended to be replaced by a trained model. Every score
ships with an explanation so HR can act on the why, not just the number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AttritionFeatures:
    employee_id: str
    name: str
    department: Optional[str] = None
    tenure_years: float = 1.0
    months_since_last_raise: float = 12.0
    months_since_last_promotion: float = 24.0
    performance_rating: float = 3.0       # 1..5
    engagement_score: Optional[float] = None  # 0..1 if available
    compa_ratio: Optional[float] = None       # salary / midpoint
    pto_balance_days: Optional[float] = None  # large unused balance can be a risk signal
    overtime_hours_last_30d: float = 0.0
    manager_change_in_last_180d: bool = False
    role_change_in_last_180d: bool = False


@dataclass
class AttritionPrediction:
    employee_id: str
    name: str
    department: Optional[str]
    risk_score: int                       # 0-100
    band: str                             # low | medium | high
    drivers: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    is_heuristic: bool = True
    note: str = (
        "Heuristic model intended for triage only. Do not use as basis for "
        "any retention compensation decision without manager + HR review."
    )

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
def _score_features(f: AttritionFeatures) -> tuple[int, list[str], list[str]]:
    score = 0
    drivers: list[str] = []
    actions: list[str] = []

    # Compensation drift
    if f.compa_ratio is not None:
        if f.compa_ratio < 0.85:
            score += 22
            drivers.append("Compa-ratio below 0.85 (under-paid vs. band midpoint).")
            actions.append("Run a compensation review with HR.")
        elif f.compa_ratio < 0.95:
            score += 10
            drivers.append("Compa-ratio below 0.95.")

    # Time since last raise
    if f.months_since_last_raise >= 18:
        score += 15
        drivers.append(f"No raise in {int(f.months_since_last_raise)} months.")
        actions.append("Confirm next merit cycle inclusion.")

    # Time since last promotion (only matters for high performers)
    if f.performance_rating >= 4 and f.months_since_last_promotion >= 24:
        score += 12
        drivers.append("Strong performer with no promotion in 24+ months.")
        actions.append("Check promotion readiness and career path conversation.")

    # Performance trend
    if f.performance_rating <= 2.5:
        score += 8
        drivers.append("Performance rating below expectations.")
        actions.append("Manager 1:1 to align on expectations and development plan.")

    # Engagement
    if f.engagement_score is not None and f.engagement_score < 0.5:
        score += 15
        drivers.append("Engagement score below 0.5.")
        actions.append("Stay interview with skip-level manager.")

    # Tenure curve — risk increases around 18-30 months
    if 1.5 <= f.tenure_years <= 2.5:
        score += 6
        drivers.append("Within the 18-30 month attrition window.")

    # Overtime
    if f.overtime_hours_last_30d > 30:
        score += 10
        drivers.append(f"{int(f.overtime_hours_last_30d)} hrs of overtime in the last 30 days.")
        actions.append("Reassess workload; ensure recovery time is taken.")

    # Manager change
    if f.manager_change_in_last_180d:
        score += 7
        drivers.append("Manager change within last 6 months.")
        actions.append("Schedule a re-onboarding 1:1 between new manager and employee.")

    if f.role_change_in_last_180d:
        score += 4
        drivers.append("Recent role change.")
        actions.append("30/60/90 check-in on the new scope.")

    # PTO hoarding can indicate burnout/exit prep
    if f.pto_balance_days is not None and f.pto_balance_days > 18:
        score += 6
        drivers.append(f"Large unused PTO balance ({f.pto_balance_days:.0f} days).")
        actions.append("Encourage a real break; large balances correlate with burnout.")

    score = max(0, min(100, score))
    return score, drivers, actions


def _band(score: int) -> str:
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def predict(f: AttritionFeatures) -> AttritionPrediction:
    score, drivers, actions = _score_features(f)
    return AttritionPrediction(
        employee_id=f.employee_id,
        name=f.name,
        department=f.department,
        risk_score=score,
        band=_band(score),
        drivers=drivers,
        suggested_actions=actions,
    )


def predict_batch(features: list[AttritionFeatures]) -> list[AttritionPrediction]:
    out = [predict(f) for f in features]
    out.sort(key=lambda p: p.risk_score, reverse=True)
    return out
