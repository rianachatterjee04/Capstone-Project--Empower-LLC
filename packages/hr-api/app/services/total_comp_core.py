"""Pure, deterministic Total-Compensation aggregation.

This module contains NO I/O and NO database access.  It takes the four already
-fetched compensation streams (cash, commission, payroll actual, equity) and
folds them into a single Total-Comp payload with a target-vs-actual view and a
component mix that sums to 100%.  Because it is pure, it is the golden-vector
surface: every number below is hand-checkable.

Money correctness rules baked in here:
  * Every component is fail-soft.  A component that could not be fetched is
    represented by a `Component(available=False, reason=...)` and contributes
    ZERO to the totals, never a crash and never a silent wrong number.
  * `target_total_comp`  = base + bonus_target + benefits + commission_target
                           + equity_annualized       (what the plan promises)
  * `actual_total_comp`  = base + bonus_actual + benefits + commission_earned_ytd
                           + payroll_actual_gross_ytd? ...  — see
    `_actual_total` for the exact, deliberate choice (payroll actual is shown
    alongside, NOT double-counted with base salary).
  * Mix percentages are computed against `target_total_comp` and always sum to
    100.0 (± rounding is corrected on the largest slice) when the target is
    positive; otherwise the mix is empty.

All rounding is to cents (2dp) and is applied ONCE, at the payload boundary, so
intermediate sums stay exact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _r(x: float) -> float:
    return round(float(x or 0.0), 2)


# ---------------------------------------------------------------------------
# Component inputs (already fetched from their real sources upstream)
# ---------------------------------------------------------------------------
@dataclass
class CashComp:
    # CommissionComp and PayrollActualComp two structs below both carry
    # available + reason, which is why the comp page can say "unavailable —
    # commission API not configured" instead of showing a zero. CashComp had
    # neither, so an employee with no comp_records row rendered "Base salary
    # $0" beside those honest lines — a statement about what they are paid,
    # made from the fact that we hold nothing.
    available: bool = False
    reason: Optional[str] = "no compensation record on file for this employee"
    base_salary: float = 0.0
    bonus_target: float = 0.0
    bonus_actual: Optional[float] = None  # None -> assume target for actual
    benefits_value: float = 0.0
    currency: str = "USD"
    as_of: Optional[str] = None


@dataclass
class CommissionComp:
    available: bool = False
    reason: Optional[str] = None
    earned_ytd: float = 0.0
    accrued_pending: float = 0.0
    plan_target: float = 0.0


@dataclass
class PayrollActualComp:
    available: bool = False
    reason: Optional[str] = None
    gross_ytd: float = 0.0


@dataclass
class EquityComp:
    available: bool = False
    reason: Optional[str] = None
    grant_value: float = 0.0       # total grant-date value across active grants
    vested_value: float = 0.0
    unvested_value: float = 0.0
    annualized: float = 0.0        # value vesting in the current plan year
    grants: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _target_total(cash: CashComp, comm: CommissionComp, eq: EquityComp) -> float:
    """What the comp plan PROMISES for the year: base + target bonus + benefits
    + target commission (if the rep is on a plan) + annualized equity."""
    total = cash.base_salary + cash.bonus_target + cash.benefits_value
    if comm.available:
        total += comm.plan_target
    if eq.available:
        total += eq.annualized
    return total


def _actual_total(cash: CashComp, comm: CommissionComp,
                  payroll: PayrollActualComp, eq: EquityComp) -> float:
    """What the person is actually tracking to.

    base salary + actual (or target) bonus + benefits + commission EARNED ytd
    + annualized equity.  Payroll gross-YTD is reported ALONGSIDE for
    reconciliation but is deliberately NOT added here: gross-YTD already
    contains base+bonus+commission that have been paid, so adding it would
    double-count.  Equity annualized is an accounting run-rate, added to keep
    actual and target on the same basis."""
    bonus = cash.bonus_actual if cash.bonus_actual is not None else cash.bonus_target
    total = cash.base_salary + (bonus or 0.0) + cash.benefits_value
    if comm.available:
        total += comm.earned_ytd
    if eq.available:
        total += eq.annualized
    return total


def _mix(target: float, slices: List[tuple]) -> Dict[str, float]:
    """Component mix as % of target total comp, guaranteed to sum to 100.0.

    `slices` is a list of (label, amount).  Zero/negative target -> {} (no
    meaningful mix).  Rounding drift is absorbed by the largest slice so the
    displayed percentages always total exactly 100.0."""
    if target <= 0:
        return {}
    pct = {label: round(amt / target * 100.0, 2) for label, amt in slices if amt}
    if not pct:
        return {}
    drift = round(100.0 - sum(pct.values()), 2)
    if drift:
        biggest = max(pct, key=lambda k: pct[k])
        pct[biggest] = round(pct[biggest] + drift, 2)
    return pct


def assemble_total_comp(
    *,
    employee_id: Optional[str],
    plan_year: int,
    cash: CashComp,
    commission: CommissionComp,
    payroll_actual: PayrollActualComp,
    equity: EquityComp,
    current_fmv: Optional[float] = None,
) -> dict:
    """Fold the four streams into the unified Total-Comp payload.

    Pure & deterministic: identical inputs always produce identical output.
    Never raises on a missing component — an unavailable stream simply
    contributes zero and is flagged so the UI can show 'source not connected'."""
    target = _target_total(cash, commission, equity)
    actual = _actual_total(cash, commission, payroll_actual, equity)

    bonus_actual = (cash.bonus_actual if cash.bonus_actual is not None
                    else cash.bonus_target)

    # Mix is built on the TARGET basis (the stable planning number).
    mix_slices = [
        ("base_salary", cash.base_salary),
        ("bonus", cash.bonus_target),
        ("benefits", cash.benefits_value),
        ("commission", commission.plan_target if commission.available else 0.0),
        ("equity", equity.annualized if equity.available else 0.0),
    ]
    mix = _mix(target, mix_slices)

    return {
        "employee_id": employee_id,
        "plan_year": plan_year,
        "currency": cash.currency,
        "current_fmv": current_fmv,
        "base_salary": _r(cash.base_salary),
        "bonus": {
            "target": _r(cash.bonus_target),
            "actual": _r(bonus_actual),
        },
        "benefits_value": _r(cash.benefits_value),
        # The flat base_salary/bonus/benefits_value fields above stay for
        # existing callers. This block is what a screen should read: it can
        # tell "we hold no comp record for this person" from "this person is
        # paid nothing", which the bare numbers cannot.
        "cash": {
            "available": cash.available,
            "reason": cash.reason,
            "base_salary": _r(cash.base_salary),
            "bonus_target": _r(cash.bonus_target),
            "bonus_actual": _r(bonus_actual),
            "benefits_value": _r(cash.benefits_value),
            "as_of": cash.as_of,
        },
        "commission": {
            "available": commission.available,
            "reason": commission.reason,
            "earned_ytd": _r(commission.earned_ytd),
            "accrued_pending": _r(commission.accrued_pending),
            "plan_target": _r(commission.plan_target),
        },
        "payroll_actual": {
            "available": payroll_actual.available,
            "source": "payroll" if payroll_actual.available else "unavailable",
            "reason": payroll_actual.reason,
            "gross_ytd": _r(payroll_actual.gross_ytd),
        },
        "equity": {
            "available": equity.available,
            "reason": equity.reason,
            "grant_value": _r(equity.grant_value),
            "vested_value": _r(equity.vested_value),
            "unvested_value": _r(equity.unvested_value),
            "annualized": _r(equity.annualized),
            "grants": equity.grants,
        },
        "totals": {
            "target_total_comp": _r(target),
            "actual_total_comp": _r(actual),
            "variance_to_target": _r(actual - target),
            "attainment_pct": (round(actual / target * 100.0, 1)
                               if target > 0 else None),
            "mix_pct_by_component": mix,
        },
        "cash_as_of": cash.as_of,
        "methodology": _methodology(cash, commission, payroll_actual, equity),
    }


def _methodology(cash, commission, payroll_actual, equity) -> str:
    """Describe how THIS response was assembled, not how the product can work.

    This string used to be a fixed paragraph naming every pay stream including
    "equity vested/unvested/annualized (HR cap-table + ASC-718 engine)". On a
    deployment built without the cap table that sentence is simply false, and it
    sat directly under a total that excluded equity -- telling the reader the
    number included something it did not. The paragraph now lists the sources
    that actually contributed and names the ones that did not, with the reason
    the caller can already see on each component.
    """
    contributing = [
        (cash.available, "base salary + bonus + benefits (HR comp records)"),
        (commission.available, "sales commission earned/accrued (commission engine)"),
        (equity.available, "equity vested/unvested/annualized (cap table + ASC-718)"),
    ]
    used = [label for ok, label in contributing if ok]
    missing = [
        (label, reason)
        for ok, label, reason in (
            (cash.available, "cash compensation", cash.reason),
            (commission.available, "commission", commission.reason),
            (payroll_actual.available, "payroll gross YTD", payroll_actual.reason),
            (equity.available, "equity", equity.reason),
        )
        if not ok
    ]

    parts = []
    if used:
        parts.append(
            "This total is assembled from: " + "; ".join(used) + "."
        )
    else:
        parts.append("No pay stream could be assembled for this employee.")

    parts.append(
        "Target uses plan targets; actual uses earned-to-date."
    )
    if payroll_actual.available:
        parts.append(
            "Payroll gross YTD is shown for reconciliation and is not re-added "
            "to the actual total (it already contains paid base/bonus/commission)."
        )
    if missing:
        parts.append(
            "Not included, because "
            + "; ".join(f"{label} is unavailable ({reason})" for label, reason in missing)
            + "."
        )
    return " ".join(parts)

