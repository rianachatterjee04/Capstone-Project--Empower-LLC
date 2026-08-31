"""Time-off accrual math — pure functions, no DB.

BambooHR-style accrual model:
- A policy grants `accrual_hours_per_period` at the END of each completed
  period (monthly | biweekly | annual), starting from the assignment's
  effective date.
- Balances are the signed sum of ledger entries (accrual +, usage -,
  adjustment +/-, carryover +/-), optionally capped by max_balance_hours.
- Usage for a PTO request = business days in range x hours_per_day.

Everything here is deterministic and unit-tested (see test_timeoff_accrual.py);
the /timeoff router is a thin DB shell around these functions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

VALID_PERIODS = ("monthly", "biweekly", "annual")


@dataclass(frozen=True)
class AccrualGrant:
    """One accrual the employee has earned: written as a ledger row with
    period_key as the idempotency key."""
    period_key: str
    hours: float
    effective_date: date  # the day the period completed


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def accrual_grants(
    effective_date: date,
    as_of: date,
    accrual_period: str,
    accrual_hours_per_period: float,
) -> list[AccrualGrant]:
    """All accruals earned between `effective_date` and `as_of` (inclusive).

    monthly  -> one grant per calendar month whose last day is <= as_of and
                whose first day is >= the month the assignment started
                (partial first months do not accrue; standard SMB policy).
    biweekly -> one grant per completed 14-day block since effective_date.
    annual   -> one grant per completed 365-day year since effective_date.
    """
    if accrual_period not in VALID_PERIODS:
        raise ValueError(f"accrual_period must be one of {VALID_PERIODS}")
    if as_of < effective_date:
        return []

    rate = float(accrual_hours_per_period)
    grants: list[AccrualGrant] = []

    if accrual_period == "monthly":
        # First full month: if assigned mid-month, accrual starts next month.
        year, month = effective_date.year, effective_date.month
        if effective_date.day > 1:
            month += 1
            if month == 13:
                year, month = year + 1, 1
        while _month_end(year, month) <= as_of:
            grants.append(AccrualGrant(
                period_key=f"{year:04d}-{month:02d}",
                hours=rate,
                effective_date=_month_end(year, month),
            ))
            month += 1
            if month == 13:
                year, month = year + 1, 1
    elif accrual_period == "biweekly":
        block_start = effective_date
        i = 1
        while block_start + timedelta(days=13) <= as_of:
            end = block_start + timedelta(days=13)
            grants.append(AccrualGrant(
                period_key=f"BW-{effective_date.isoformat()}-{i:03d}",
                hours=rate,
                effective_date=end,
            ))
            block_start = end + timedelta(days=1)
            i += 1
    else:  # annual
        year_start = effective_date
        i = 1
        while True:
            try:
                end = year_start.replace(year=year_start.year + 1) - timedelta(days=1)
            except ValueError:  # Feb 29 anniversary
                end = date(year_start.year + 1, 2, 28)
            if end > as_of:
                break
            grants.append(AccrualGrant(
                period_key=f"YR-{effective_date.isoformat()}-{i:03d}",
                hours=rate,
                effective_date=end,
            ))
            year_start = end + timedelta(days=1)
            i += 1

    return grants


def business_days(start: date, end: date) -> int:
    """Weekdays (Mon-Fri) in [start, end], inclusive. 0 if end < start."""
    if end < start:
        return 0
    days = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def usage_hours(start: date, end: date, hours_per_day: float) -> float:
    """Hours consumed by a PTO request (business days x hours/day)."""
    return round(business_days(start, end) * float(hours_per_day), 2)


def compute_balance(entries: list[dict | tuple], max_balance_hours: float | None = None) -> float:
    """Signed sum of ledger hours. Entries are dicts with 'hours' (or bare
    numbers). If max_balance_hours is set, the result is capped at it —
    the cap applies to the NET balance (simple SMB semantics)."""
    total = Decimal("0")
    for e in entries:
        if isinstance(e, dict):
            total += Decimal(str(e.get("hours", 0)))
        else:
            total += Decimal(str(e))
    bal = float(total)
    if max_balance_hours is not None:
        bal = min(bal, float(max_balance_hours))
    return round(bal, 2)


def cap_new_accrual(current_balance: float, grant_hours: float,
                    max_balance_hours: float | None) -> float:
    """Hours of a new accrual grant that actually fit under the cap.
    Returns a value in [0, grant_hours]."""
    if max_balance_hours is None:
        return round(float(grant_hours), 2)
    room = float(max_balance_hours) - float(current_balance)
    return round(max(0.0, min(float(grant_hours), room)), 2)


def carryover_hours(year_end_balance: float, carryover_max_hours: float | None) -> float:
    """Hours that survive a year boundary. NULL cap = everything carries.
    Returns the (non-negative) carried-over balance."""
    bal = max(0.0, float(year_end_balance))
    if carryover_max_hours is None:
        return round(bal, 2)
    return round(min(bal, float(carryover_max_hours)), 2)
