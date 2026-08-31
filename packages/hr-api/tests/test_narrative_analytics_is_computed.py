"""
Nothing on the narrative-analytics page is asserted without a query behind it.

WHY THIS IS A TEST
Two of the four insights this service returned were invented end to end:

  "Engineering attrition signal is rising, concentrated on senior ICs ... Two of
   three high-risk employees are sub-band on comp and overdue for a promotion
   conversation."  metric "2 of 3 in Eng", delta "up 1 vs. last month", trend
   [0,0,1,1,2,2,3]

  "Loaded annual payroll is 17% under the $2.4M comp envelope ... Q3 comp cycle
   adds another 3%."  metric "-17.3%", trend [1.7, 1.8, 1.85, 1.9, 1.92, 1.95, 1.98]

Neither ran a single query. The demo organisation has one employee — a CDL
driver — and no engineering department. The page's own subtitle promised "what's
changed, why, and what AI suggests next", and the attrition card recommended
running a comp review and booking stay interviews.

The other two mixed real counts with invented detail and drew six invented
history points followed by one real value as a trend line.

The rule this pins: an insight exists only when a query produced it, and it
names that query. With no data, the page shows nothing rather than something.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import narrative_analytics_service as N

ORG = "11111111-1111-1111-1111-111111111111"


class _DeadDB:
    """A session where every query fails.

    _scalar and _monthly both swallow exceptions and report "no data", so this
    is the strongest possible statement of the rule: given nothing, invent
    nothing.
    """

    async def execute(self, *a, **k):
        raise RuntimeError("no database")


def _build(db):
    # asyncio.run(), not get_event_loop(): run alone this file passed, and in
    # the full suite it raised "There is no current event loop in thread" four
    # times, because pytest-asyncio had closed the loop other tests used.
    # A test that only passes when it runs first is not a passing test.
    return asyncio.run(N.build(db, ORG))


@pytest.fixture
def dead():
    return _build(_DeadDB())


def test_no_data_means_no_insights(dead):
    assert dead["insights"] == [], (
        "insights were produced with no query results behind them:\n  "
        + "\n  ".join(i["headline"] for i in dead["insights"]))


def test_the_two_fabricated_insights_are_gone(dead):
    blob = repr(dead).lower()
    for gone in ("senior ic", "2 of 3 in eng", "comp envelope", "-17.3",
                 "sub-band", "stay interview", "soc 2", "customer success"):
        assert gone not in blob, f"{gone!r} is still asserted by this service"


def test_what_cannot_be_computed_is_named_with_a_reason(dead):
    topics = {u["topic"] for u in dead["unavailable"]}
    assert "Attrition risk" in topics
    assert "Payroll against budget" in topics
    for u in dead["unavailable"]:
        assert u["reason"].strip(), f"{u['topic']} gives no reason"
        assert u["needs"].strip(), f"{u['topic']} does not say what it would take"


def test_the_source_module_hardcodes_no_trend_series():
    """No literal multi-point series may be handed to a chart.

    The old code drew [0,0,1,1,2,2,3] and [1.7, ..., 1.98] as if they were
    history. A chart on this page comes from _monthly() or it does not exist.
    """
    import inspect
    import re
    src = inspect.getsource(N)
    # strip the docstring, which quotes the old series on purpose
    body = src.split('"""', 2)[-1]
    literal_series = re.findall(r"series\s*=\s*\[[^\]]*,[^\]]*\]", body)
    assert literal_series == [], (
        f"hard-coded chart series are back: {literal_series}")


class _CountingDB:
    """Returns a fixed count for every scalar query and no rows for history."""

    def __init__(self, n):
        self.n = n
        self.queries = []

    async def execute(self, stmt, params=None):
        self.queries.append(str(stmt))
        n = self.n

        class R:
            def first(self_inner):
                return (n,)

            def mappings(self_inner):
                class M:
                    def all(self_m):
                        return []
                return M()
        return R()


def test_every_insight_names_the_query_it_came_from():
    """CONTROL. With data present, insights appear — and each cites a source."""
    db = _CountingDB(4)
    out = _build(db)
    assert out["insights"], "no insights were produced even with data present"
    for i in out["insights"]:
        assert i.get("evidence", "").strip(), (
            f"insight {i['id']!r} does not say what it was computed from")
    # ...and every number it printed came from a query, not a constant.
    assert db.queries, "insights were produced without executing any query"
