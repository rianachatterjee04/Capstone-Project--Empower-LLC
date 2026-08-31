"""Effective-dated record helpers (PeopleSoft pattern) — pure functions.

A "record" is any dict with `effective_date` (date) and optional `end_date`
(date | None; None = open/current). Used for comp_history and job_history.

Rules:
- At most one open record per employee per history type.
- Inserting a new record with effective date E closes the previous open
  record at E - 1 day.
- `resolve_as_of(records, d)` returns the record in force on day d.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping, Optional, Sequence


def _eff(r: Mapping[str, Any]) -> date:
    return r["effective_date"]


def _end(r: Mapping[str, Any]) -> Optional[date]:
    return r.get("end_date")


def resolve_as_of(records: Sequence[Mapping[str, Any]], as_of: date) -> Optional[Mapping[str, Any]]:
    """The record in force on `as_of`: the latest record whose
    effective_date <= as_of and (end_date is None or end_date >= as_of)."""
    candidates = [
        r for r in records
        if _eff(r) <= as_of and (_end(r) is None or _end(r) >= as_of)
    ]
    if not candidates:
        return None
    return max(candidates, key=_eff)


def closing_end_date(new_effective_date: date) -> date:
    """End date to stamp on the previous open record when a new record
    becomes effective: the day before."""
    return new_effective_date - timedelta(days=1)


def validate_new_record(records: Sequence[Mapping[str, Any]], new_effective_date: date) -> None:
    """Raise ValueError if the new effective date does not move history
    forward (it must be after every existing effective date)."""
    for r in records:
        if _eff(r) >= new_effective_date:
            raise ValueError(
                "effective_date must be after the latest record "
                f"({_eff(r).isoformat()} >= {new_effective_date.isoformat()})"
            )


def build_timeline(records: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Records sorted by effective_date ascending with computed end dates:
    each record ends the day before the next one starts (last stays open
    unless it already has an end_date). Non-destructive: returns copies."""
    ordered = sorted((dict(r) for r in records), key=_eff)
    for i, r in enumerate(ordered):
        if i + 1 < len(ordered):
            r["end_date"] = closing_end_date(_eff(ordered[i + 1]))
    return ordered
