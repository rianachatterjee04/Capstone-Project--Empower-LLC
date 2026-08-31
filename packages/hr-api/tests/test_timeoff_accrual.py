"""Unit tests for app/services/timeoff_service.py (pure accrual math).

Run: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest test_timeoff_accrual.py
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.timeoff_service import (
    accrual_grants,
    business_days,
    cap_new_accrual,
    carryover_hours,
    compute_balance,
    usage_hours,
)


# ---------------------------------------------------------------- accruals
def test_monthly_accrual_full_months():
    # Assigned Jan 1, as of Mar 31 -> Jan, Feb, Mar all accrue.
    grants = accrual_grants(date(2026, 1, 1), date(2026, 3, 31), "monthly", 6.67)
    assert [g.period_key for g in grants] == ["2026-01", "2026-02", "2026-03"]
    assert all(g.hours == 6.67 for g in grants)
    assert grants[0].effective_date == date(2026, 1, 31)


def test_monthly_accrual_partial_first_month_skipped():
    # Assigned mid-January -> first accrual is February.
    grants = accrual_grants(date(2026, 1, 15), date(2026, 3, 31), "monthly", 8)
    assert [g.period_key for g in grants] == ["2026-02", "2026-03"]


def test_monthly_accrual_incomplete_month_not_granted():
    # As of Mar 30 the March period hasn't completed.
    grants = accrual_grants(date(2026, 1, 1), date(2026, 3, 30), "monthly", 8)
    assert [g.period_key for g in grants] == ["2026-01", "2026-02"]


def test_monthly_accrual_year_rollover():
    grants = accrual_grants(date(2025, 11, 1), date(2026, 2, 28), "monthly", 4)
    assert [g.period_key for g in grants] == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_biweekly_accrual_blocks():
    # 4 weeks = exactly two 14-day blocks.
    grants = accrual_grants(date(2026, 6, 1), date(2026, 6, 28), "biweekly", 3.08)
    assert len(grants) == 2
    assert grants[0].effective_date == date(2026, 6, 14)
    assert grants[1].effective_date == date(2026, 6, 28)
    # keys are unique + deterministic
    assert len({g.period_key for g in grants}) == 2


def test_annual_accrual_only_after_full_year():
    assert accrual_grants(date(2025, 7, 1), date(2026, 6, 29), "annual", 80) == []
    grants = accrual_grants(date(2025, 7, 1), date(2026, 6, 30), "annual", 80)
    assert len(grants) == 1 and grants[0].hours == 80


def test_accrual_before_effective_date_is_empty():
    assert accrual_grants(date(2026, 5, 1), date(2026, 4, 1), "monthly", 8) == []


def test_accrual_invalid_period_raises():
    with pytest.raises(ValueError):
        accrual_grants(date(2026, 1, 1), date(2026, 2, 1), "weekly", 8)


# ---------------------------------------------------------------- usage
def test_business_days_excludes_weekends():
    # Mon 2026-07-06 .. Sun 2026-07-12 -> 5 weekdays
    assert business_days(date(2026, 7, 6), date(2026, 7, 12)) == 5
    # Sat..Sun -> 0
    assert business_days(date(2026, 7, 11), date(2026, 7, 12)) == 0
    # inverted range -> 0
    assert business_days(date(2026, 7, 12), date(2026, 7, 6)) == 0


def test_usage_hours_uses_hours_per_day():
    # Wed..Fri = 3 business days x 8h
    assert usage_hours(date(2026, 7, 8), date(2026, 7, 10), 8) == 24.0
    # half-day schedule
    assert usage_hours(date(2026, 7, 8), date(2026, 7, 10), 4) == 12.0


# ---------------------------------------------------------------- balance
def test_compute_balance_signed_sum():
    entries = [
        {"hours": 6.67}, {"hours": 6.67}, {"hours": -8.0}, {"hours": 2.0},
    ]
    assert compute_balance(entries) == 7.34


def test_compute_balance_cap():
    entries = [{"hours": 100}, {"hours": 60}]
    assert compute_balance(entries, max_balance_hours=120) == 120.0
    assert compute_balance(entries, max_balance_hours=None) == 160.0


def test_cap_new_accrual_partial_and_zero_room():
    assert cap_new_accrual(118, 6.67, 120) == 2.0
    assert cap_new_accrual(120, 6.67, 120) == 0.0
    assert cap_new_accrual(50, 6.67, None) == 6.67
    # never negative even if already over the cap (manual adjustments)
    assert cap_new_accrual(130, 6.67, 120) == 0.0


def test_carryover_hours():
    assert carryover_hours(75, 40) == 40.0
    assert carryover_hours(30, 40) == 30.0
    assert carryover_hours(30, None) == 30.0
    assert carryover_hours(-5, 40) == 0.0
