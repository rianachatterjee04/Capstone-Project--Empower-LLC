"""The cap table is not part of this build, and must not come back.

WHY THIS EXISTS
The equity module was removed by deleting the obvious things: the engine, the
router, the migrations, the frontends' pages. That left, undetected and reached
only by hand-searching three separate times:

  * app/platform/platform.py -- a multi-company cap table and option-grant
    engine (share classes, strike prices, vesting schedules) that seeded a demo
    cap table with named holders at import time, live behind two routers;
  * app/models/multi_entity_support.py -- combined_cap_table() across entities;
  * app/models/investor_portal.py -- "Dilution Modeling";
  * app/models/education_chatbot.py -- an assistant that explained what happens
    to unvested shares, on a system holding no equity data;
  * a ShareClass vocabulary and a VESTING_EVENT ledger type;
  * a board narrative that reported "equity burn was 0.00% with YTD dilution at
    0.00%" on every HR board report, computed from keys nobody supplies.

Deleting a feature is not the same as removing its concepts, and none of those
were caught by 1337 passing tests. This guard is the thing that notices.

It reads CODE ONLY -- comments and docstrings stripped -- so the paragraph above
does not fire it. That is not a detail: five earlier guards in this repo failed
on their first run against the comment written to explain them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ._source_scan import code_only

APP = Path(__file__).resolve().parent.parent / "app"

# Concepts that only exist to serve a cap table. "equity" alone is deliberately
# NOT here: pay equity (fairness across cohorts) is a real HR feature in this
# build, and a guard that cannot tell the two apart would either be switched off
# or would push people to rename a legitimate feature.
BANNED = re.compile(
    r"cap_?table|captable|409a|asc.?718|share_?class|strike_?price"
    r"|vesting_?(schedule|months|event)|option_?pool|dilution",
    re.IGNORECASE,
)


def _python_sources():
    for p in sorted(APP.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p


def _hits(path: Path) -> list[str]:
    code = code_only(path.read_text(errors="replace"))
    return sorted({m.group(0) for m in BANNED.finditer(code)})


def test_no_cap_table_concepts_in_hr_api_code():
    offenders = {}
    for path in _python_sources():
        hits = _hits(path)
        if hits:
            offenders[str(path.relative_to(APP.parent))] = hits
    assert not offenders, (
        "cap-table concepts are present in a build that ships no cap table:\n"
        + "\n".join(f"  {f}: {', '.join(h)}" for f, h in offenders.items())
    )


def test_the_equity_module_and_its_router_are_absent():
    assert not (APP / "equity").exists(), "app/equity/ is back"
    assert not (APP / "api" / "routers" / "equity.py").exists(), "the equity router is back"


def test_no_equity_migration_is_present():
    migrations = APP.parent / "migrations"
    back = [p.name for p in migrations.glob("*.sql") if "equity" in p.name.lower()]
    assert not back, f"equity migrations are back: {back}"


def test_total_comp_reports_equity_unavailable_with_a_reason():
    """Removing the cap table must leave an explanation, not a zero."""
    from app.services.total_comp_service import EQUITY_UNAVAILABLE_REASON

    assert EQUITY_UNAVAILABLE_REASON.strip(), "the reason string is empty"
    assert "cap table" in EQUITY_UNAVAILABLE_REASON.lower()


# --- controls -------------------------------------------------------------
# A detector nobody has seen fail is not evidence. These pin both directions.

def test_CONTROL_positive_detector_catches_what_it_must():
    for planted in (
        "cap_table = {}",
        "class Grant:\n    strike_price = 1.25\n",
        'SHARE_CLASS = "Common"',
        "def vesting_schedule(): pass",
        "option_pool_size = 10",
        "dilution_pct = 0.2",
    ):
        assert BANNED.search(code_only(planted)), f"detector missed: {planted!r}"


def test_CONTROL_negative_pay_equity_is_not_flagged():
    for allowed in (
        "def pay_equity_cohort(): pass",
        "equity_health_index = 0.9",
        "from app.services.pay_equity_service import analyse",
        "compensation_band = 3",
    ):
        assert not BANNED.search(code_only(allowed)), f"false positive on: {allowed!r}"


def test_CONTROL_a_banned_word_in_a_comment_does_not_fire():
    src = '# we used to compute a cap_table here\nx = 1\n'
    assert not BANNED.search(code_only(src)), "the guard fires on its own prose"
    assert BANNED.search(src), "and the raw text really does contain the word"
