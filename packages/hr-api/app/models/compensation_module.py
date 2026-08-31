"""Total Compensation View.

Historically this summed only salary + bonus + equity + benefits.  The unified
Total-Comp view now aggregates EVERY pay stream from its real source — sales
commission and payroll actuals as well — via the deterministic
aggregator in `app.services.total_comp_core` and the fetching shell in
`app.services.total_comp_service`.  The class below is kept for backward
compatibility and now delegates its summary to the same pure core so there is
ONE source of truth for the math.
"""
from __future__ import annotations

from app.services import total_comp_core as _core


class TotalCompensation:
    """Legacy 4-component view (salary + bonus + equity + benefits).

    Retained for callers that only have the four cash-ish numbers.  For the full
    unified view (commission + payroll actuals + equity vested/unvested/
    annualized + target-vs-actual) use
    `app.services.total_comp_service.build_total_comp`.
    """

    def __init__(self, salary, bonus, equity_value, benefits_value):
        self.salary = salary
        self.bonus = bonus
        self.equity_value = equity_value
        self.benefits_value = benefits_value

    def total_comp(self):
        return self.salary + self.bonus + self.equity_value + self.benefits_value

    def comp_summary(self):
        return {
            "Salary": self.salary,
            "Bonus": self.bonus,
            "Equity": self.equity_value,
            "Benefits": self.benefits_value,
            "Total": self.total_comp(),
        }

    def unified_summary(self, *, plan_year: int,
                        commission_earned_ytd: float = 0.0,
                        commission_accrued: float = 0.0,
                        commission_target: float = 0.0,
                        commission_available: bool = False,
                        payroll_gross_ytd: float = 0.0,
                        payroll_available: bool = False,
                        equity_vested: float = 0.0,
                        equity_unvested: float = 0.0,
                        equity_annualized: float | None = None,
                        currency: str = "USD"):
        """Full, unified total-comp payload built from this object's cash fields
        plus optional commission / payroll / equity streams.  Delegates entirely
        to the pure, golden-vector-tested core aggregator."""
        annual_equity = (equity_annualized
                         if equity_annualized is not None else self.equity_value)
        return _core.assemble_total_comp(
            employee_id=None,
            plan_year=plan_year,
            cash=_core.CashComp(base_salary=self.salary, bonus_target=self.bonus,
                                benefits_value=self.benefits_value, currency=currency),
            commission=_core.CommissionComp(
                available=commission_available, earned_ytd=commission_earned_ytd,
                accrued_pending=commission_accrued, plan_target=commission_target),
            payroll_actual=_core.PayrollActualComp(
                available=payroll_available, gross_ytd=payroll_gross_ytd),
            equity=_core.EquityComp(
                available=(equity_annualized is not None
                           or self.equity_value != 0 or equity_vested != 0),
                grant_value=self.equity_value,
                vested_value=equity_vested, unvested_value=equity_unvested,
                annualized=annual_equity),
        )
