"""Unit tests for app/services/effective_dating.py (PeopleSoft pattern).

Run: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest test_effective_dating.py
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.effective_dating import (
    build_timeline,
    closing_end_date,
    resolve_as_of,
    validate_new_record,
)


HISTORY = [
    {"amount": 90000, "effective_date": date(2024, 1, 1), "end_date": date(2024, 12, 31)},
    {"amount": 98000, "effective_date": date(2025, 1, 1), "end_date": date(2025, 6, 30)},
    {"amount": 105000, "effective_date": date(2025, 7, 1), "end_date": None},
]


def test_resolve_as_of_picks_record_in_force():
    assert resolve_as_of(HISTORY, date(2024, 6, 15))["amount"] == 90000
    assert resolve_as_of(HISTORY, date(2025, 3, 1))["amount"] == 98000
    assert resolve_as_of(HISTORY, date(2026, 7, 7))["amount"] == 105000


def test_resolve_as_of_boundary_days():
    # effective day itself and end day itself are both in force
    assert resolve_as_of(HISTORY, date(2025, 1, 1))["amount"] == 98000
    assert resolve_as_of(HISTORY, date(2025, 6, 30))["amount"] == 98000
    assert resolve_as_of(HISTORY, date(2025, 7, 1))["amount"] == 105000


def test_resolve_as_of_before_first_record_is_none():
    assert resolve_as_of(HISTORY, date(2023, 12, 31)) is None
    assert resolve_as_of([], date(2026, 1, 1)) is None


def test_closing_end_date_is_day_before():
    assert closing_end_date(date(2026, 7, 1)) == date(2026, 6, 30)
    assert closing_end_date(date(2026, 1, 1)) == date(2025, 12, 31)


def test_validate_new_record_rejects_backdated():
    with pytest.raises(ValueError):
        validate_new_record(HISTORY, date(2025, 7, 1))   # same as latest
    with pytest.raises(ValueError):
        validate_new_record(HISTORY, date(2025, 1, 1))   # older
    validate_new_record(HISTORY, date(2026, 8, 1))       # forward: OK
    validate_new_record([], date(2020, 1, 1))            # first record: OK


def test_build_timeline_computes_end_dates():
    unordered = [
        {"amount": 105000, "effective_date": date(2025, 7, 1), "end_date": None},
        {"amount": 90000, "effective_date": date(2024, 1, 1), "end_date": None},
        {"amount": 98000, "effective_date": date(2025, 1, 1), "end_date": None},
    ]
    tl = build_timeline(unordered)
    assert [r["amount"] for r in tl] == [90000, 98000, 105000]
    assert tl[0]["end_date"] == date(2024, 12, 31)
    assert tl[1]["end_date"] == date(2025, 6, 30)
    assert tl[2]["end_date"] is None  # latest stays open
    # non-destructive
    assert unordered[0]["end_date"] is None
