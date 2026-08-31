"""
The people calendar distinguishes its own entries from the reader's.

WHY THIS IS A TEST
The timeline mixed events read from this organisation's records — PTO
requests, employee start dates, onboarding packets — with eight literals:

    "Diego Marin · offer expires"        Mid-market AE; needs CFO sign-off.
    "SOC 2 training due"                 3 employees overdue.
    "Avery Chen onboarding · Day 1"      Equipment shipped; buddy assigned.
    "Riley Singh · 30-day check-in"

Nothing distinguished them. "3 employees overdue" is a compliance claim, made
for an organisation with one employee and no such training record, sitting on
the same line as that employee's real time off.

Deleting them would leave a calendar demonstrating nothing, so they are marked
and the page badges them.
"""
from __future__ import annotations

import asyncio

from app.services import calendar_service as C

ORG = "11111111-1111-1111-1111-111111111111"


class _EmptyDB:
    """No PTO, no employees, no packets — only the shipped entries remain."""

    async def execute(self, *a, **k):
        class Res:
            def mappings(self_inner):
                class M:
                    def all(self_m):
                        return []
                return M()
        return Res()


def _events():
    out = asyncio.run(C.upcoming(_EmptyDB(), ORG, days=90))
    return out["items"] if "items" in out else out["events"]


def test_every_shipped_event_is_marked_as_a_sample():
    events = _events()
    assert events, "no events at all — this test would pass vacuously"
    unmarked = [e["title"] for e in events if not e.get("is_sample")]
    assert unmarked == [], (
        "these are literals in calendar_service and are not marked as samples, "
        f"so they read as this organisation's own events: {unmarked}")


def test_the_compliance_claim_is_among_them():
    """The one that matters most: '3 employees overdue' for a company of one."""
    events = _events()
    soc2 = [e for e in events if "SOC 2" in e["title"]]
    assert soc2, "the SOC 2 entry is gone; update this test or the fixture"
    assert soc2[0]["is_sample"] is True


def test_real_events_are_not_marked_as_samples():
    """CONTROL. The marking must not be applied to everything.

    A calendar where every entry says "sample" tells a reader nothing, and
    would hide their own time off behind a disclaimer.
    """
    import inspect
    src = inspect.getsource(C.upcoming)
    # The PTO/anniversary/onboarding branches build CalendarEvent without it.
    assert src.count("is_sample=True") == 1, (
        "is_sample is set in more than one place; only the shipped cycle_events "
        "list should carry it")
