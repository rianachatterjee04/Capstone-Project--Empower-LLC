"""AI compensation review assistant.

Given an employee snapshot + market band + performance signals, generate a
structured merit / promotion recommendation with explainable reasoning, pay
equity flags, and a confidence band. The AI never finalises a decision — it
always defers to HR/admin approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompInput:
    employee_id: str
    name: str
    job_title: str
    department: Optional[str]
    current_salary: float
    currency: str = "USD"
    tenure_years: float = 1.0
    performance_rating: float = 3.0     # 1.0 - 5.0
    last_review_summary: str = ""
    market_p25: Optional[float] = None
    market_p50: Optional[float] = None
    market_p75: Optional[float] = None
    market_p90: Optional[float] = None
    band_min: Optional[float] = None
    band_max: Optional[float] = None
    cohort_median: Optional[float] = None   # median salary of peers in same role/dept
    promotion_ready: bool = False


@dataclass
class CompRecommendation:
    employee_id: str
    current_salary: float
    suggested_low: float
    suggested_mid: float
    suggested_high: float
    merit_percent_low: float
    merit_percent_mid: float
    merit_percent_high: float
    compa_ratio: Optional[float]
    market_position: Optional[str]
    promotion_recommended: bool
    equity_flags: list[str] = field(default_factory=list)
    rationale: str = ""
    confidence: str = "medium"            # low | medium | high
    requires_approval_by: list[str] = field(default_factory=lambda: ["manager", "hr"])
    disclaimer: str = (
        "AI assistant recommendation. Final compensation decisions require human "
        "approval per the org's comp policy. Do not auto-apply."
    )

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
def _market_position(salary: float, ci: CompInput) -> Optional[str]:
    if ci.market_p50 is None:
        return None
    if ci.market_p25 and salary < ci.market_p25:
        return "below_p25"
    if ci.market_p75 and salary >= ci.market_p75:
        return "at_or_above_p75"
    if salary < ci.market_p50:
        return "p25_to_p50"
    return "p50_to_p75"


def _compa_ratio(salary: float, ci: CompInput) -> Optional[float]:
    if ci.band_min and ci.band_max and ci.band_max > ci.band_min:
        mid = (ci.band_min + ci.band_max) / 2
        return round(salary / mid, 3)
    if ci.market_p50:
        return round(salary / ci.market_p50, 3)
    return None


def _base_merit_range(perf: float) -> tuple[float, float, float]:
    """Translate a 1-5 rating into a (low, mid, high) merit percent range."""
    perf = max(1.0, min(5.0, perf))
    if perf >= 4.5:
        return (5.0, 8.0, 12.0)
    if perf >= 4.0:
        return (4.0, 6.0, 9.0)
    if perf >= 3.5:
        return (3.0, 4.5, 6.0)
    if perf >= 3.0:
        return (2.0, 3.0, 4.5)
    if perf >= 2.5:
        return (1.0, 1.5, 2.5)
    return (0.0, 0.0, 1.0)


def _equity_flags(ci: CompInput, suggested_mid: float) -> list[str]:
    flags: list[str] = []
    if ci.market_p25 and ci.current_salary < ci.market_p25:
        flags.append("below_market_p25: investigate for pay equity")
    if ci.cohort_median and ci.current_salary < 0.9 * ci.cohort_median:
        flags.append("below_peer_cohort_median: possible internal equity issue")
    if ci.market_p50 and suggested_mid < 0.85 * ci.market_p50 and ci.performance_rating >= 3.5:
        flags.append("strong_performer_underpaid: suggested still trails market")
    if ci.band_max and suggested_mid > ci.band_max:
        flags.append("range_violation: suggested mid exceeds band max — promotion needed")
    return flags


def _confidence(ci: CompInput) -> str:
    have_market = ci.market_p50 is not None
    have_band = ci.band_min is not None and ci.band_max is not None
    have_perf = ci.performance_rating >= 1.0
    score = sum([have_market, have_band, have_perf, bool(ci.last_review_summary)])
    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"


def recommend(ci: CompInput) -> CompRecommendation:
    low, mid, high = _base_merit_range(ci.performance_rating)

    # Adjust for market position
    pos = _market_position(ci.current_salary, ci)
    if pos == "below_p25":
        mid += 2.0
        high += 3.0
    elif pos == "at_or_above_p75":
        # already well-paid, slow the curve
        mid = max(0.0, mid - 1.0)
        high = max(low, high - 2.0)

    # Tenure adjustment — small bump for >= 3 yrs without recent significant raise
    if ci.tenure_years >= 3:
        mid += 0.5
        high += 1.0

    suggested_low = ci.current_salary * (1 + low / 100)
    suggested_mid = ci.current_salary * (1 + mid / 100)
    suggested_high = ci.current_salary * (1 + high / 100)

    # Cap at band max if known
    if ci.band_max:
        suggested_high = min(suggested_high, ci.band_max * 1.02)
        suggested_mid = min(suggested_mid, ci.band_max)
        suggested_low = min(suggested_low, ci.band_max)

    flags = _equity_flags(ci, suggested_mid)
    promotion_recommended = (
        ci.promotion_ready
        or (ci.performance_rating >= 4.5 and ci.tenure_years >= 2)
        or any("range_violation" in f for f in flags)
    )

    compa = _compa_ratio(ci.current_salary, ci)

    rationale_parts = [
        f"Performance {ci.performance_rating:.1f}/5 maps to base merit range {low:.0f}–{high:.0f}%."
    ]
    if pos:
        rationale_parts.append(f"Current salary sits in market band {pos.replace('_', ' ')}.")
    if ci.tenure_years >= 3:
        rationale_parts.append(f"Tenure adjustment applied ({ci.tenure_years:.0f} years).")
    if flags:
        rationale_parts.append("Equity considerations: " + "; ".join(flags) + ".")
    if promotion_recommended:
        rationale_parts.append("Promotion is recommended; suggested ranges assume new band.")
    if ci.last_review_summary:
        rationale_parts.append("Latest review highlight: " + ci.last_review_summary[:200])

    return CompRecommendation(
        employee_id=ci.employee_id,
        current_salary=round(ci.current_salary, 2),
        suggested_low=round(suggested_low, 2),
        suggested_mid=round(suggested_mid, 2),
        suggested_high=round(suggested_high, 2),
        merit_percent_low=round(low, 2),
        merit_percent_mid=round(mid, 2),
        merit_percent_high=round(high, 2),
        compa_ratio=compa,
        market_position=pos,
        promotion_recommended=promotion_recommended,
        equity_flags=flags,
        rationale=" ".join(rationale_parts),
        confidence=_confidence(ci),
    )


def recommend_batch(inputs: list[CompInput]) -> list[CompRecommendation]:
    return [recommend(ci) for ci in inputs]
