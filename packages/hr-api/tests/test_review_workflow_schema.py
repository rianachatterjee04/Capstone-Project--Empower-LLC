"""
The performance-review workflow's columns exist, and its decision constraint
matches the values the code writes.

WHY THIS IS A TEST
GET /api/reviews returned 500:

    column "ai_decision" does not exist

and it was not one column. app/api/routers/reviews.py reads or writes
ai_decision, ai_flags, self_submitted_at, manager_submitted_at, finalized_at
and manager_review against a table that had only id, org_id, employee_id,
cycle, status, rating, reviewer_id, notes and timestamps. Three endpoints were
broken — the list, the finalize, and the calibration roll-up — and the
Performance page hid it behind "No review cycle is running yet", which is
exactly what an empty list looks like.

THE CONSTRAINT IS THE SECOND HALF. Adding the columns, I wrote a CHECK on
ai_decision with a plausible-sounding vocabulary — retain / watch / exit_risk —
without reading what finalize actually writes, which is normal / pip /
promotion. That constraint would have turned a fixed endpoint into a failing
one. A vocabulary belongs to the code that writes it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROUTER = (Path(__file__).resolve().parents[1]
          / "app" / "api" / "routers" / "reviews.py")
MIGRATION = (Path(__file__).resolve().parents[1] / "migrations"
             / "20260830_performance_review_workflow_columns.sql")

REQUIRED_COLUMNS = ("self_submitted_at", "manager_submitted_at", "finalized_at",
                    "manager_review", "ai_decision", "ai_flags")


def test_the_migration_adds_every_column_the_router_uses():
    sql = MIGRATION.read_text()
    missing = [c for c in REQUIRED_COLUMNS if c not in sql]
    assert missing == [], f"the migration does not add: {missing}"


def test_the_router_still_uses_those_columns():
    """CONTROL. If the router stops using them, this migration is dead weight."""
    src = ROUTER.read_text()
    unused = [c for c in REQUIRED_COLUMNS if c not in src]
    assert unused == [], (
        f"the router no longer references {unused}; either the workflow "
        "changed or this test is now pinning columns nobody reads")


def _decisions_the_code_writes() -> set[str]:
    """Every literal assigned to `decision` in the finalize endpoint."""
    src = ROUTER.read_text()
    return set(re.findall(r'^\s*decision\s*=\s*"([a-z_]+)"', src, re.M))


def test_the_check_constraint_allows_exactly_what_finalize_writes():
    written = _decisions_the_code_writes()
    assert written, "no decision literals found; the extraction has rotted"

    sql = MIGRATION.read_text()
    m = re.search(r"ai_decision IN \(([^)]*)\)", sql)
    assert m, "the ai_decision CHECK is no longer declared the way this reads it"
    allowed = set(re.findall(r"'([a-z_]+)'", m.group(1)))

    assert written <= allowed, (
        f"finalize writes {sorted(written - allowed)}, which the CHECK "
        "constraint rejects — every finalize would fail")
    assert allowed <= written, (
        f"the CHECK allows {sorted(allowed - written)}, which nothing writes. "
        "An invented vocabulary in a constraint is how the next reader learns "
        "the wrong set of values")
