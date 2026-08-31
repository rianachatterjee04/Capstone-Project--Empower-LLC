"""
The two ways of provisioning this database agree about column types.

WHY THIS IS A TEST
performance_reviews is defined twice:

    migrations/20260630_create_performance_and_comp.sql   10 columns
    init_db_fixed.py, raw SQL after create_all            19 columns

CREATE TABLE IF NOT EXISTS makes the second a no-op wherever the first ran, so
which shape you get depends on how the database was built:

    bootstrap_hr.sh              init_db_fixed.py then migrations  -> 19
    ephemeral_interview_db.sh    create_all then migrations only   -> 10

and the second is the path docs/DEMO.md tells an operator to use. That is why
GET /api/reviews returned 500 on the demo database and not in the tests.

The ADD COLUMN migration exists to converge the two. Its types have to match
init_db_fixed.py exactly, or the paths diverge in a worse way: I first wrote
manager_review as text where the initialiser has jsonb, and the finalize
endpoint passes that value straight into performance_discrepancy_flags(...) as
a mapping. Two provisioning paths disagreeing about a TYPE fails later and
further from the cause than one of them missing the column.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "init_db_fixed.py"
MIGRATION = ROOT / "migrations" / "20260830_performance_review_workflow_columns.sql"


def _init_columns(table: str) -> dict[str, str]:
    src = INIT.read_text()
    i = src.lower().find(f"create table if not exists public.{table}")
    assert i >= 0, f"{table} is no longer created in init_db_fixed.py"
    body = src[i:i + 1600]
    cols: dict[str, str] = {}
    for line in body.splitlines()[1:]:
        line = line.split("--")[0].strip().rstrip(",")
        if not line or line.startswith((")", "constraint", "primary key", "unique")):
            if line.startswith(")"):
                break
            continue
        parts = line.split()
        if len(parts) >= 2:
            cols[parts[0].lower()] = parts[1].lower().rstrip(",")
    return cols


def _migration_columns() -> dict[str, str]:
    sql = MIGRATION.read_text()
    m = re.search(r"ALTER TABLE public\.performance_reviews\s*(.*?);", sql, re.S)
    assert m, "the ALTER is no longer declared the way this test reads it"
    cols = {}
    for line in m.group(1).splitlines():
        mm = re.search(r"ADD COLUMN IF NOT EXISTS\s+(\w+)\s+([a-z]+)", line, re.I)
        if mm:
            cols[mm.group(1).lower()] = mm.group(2).lower()
    return cols


def test_the_extraction_finds_both_definitions():
    """CONTROL. Either side coming back empty makes the comparison vacuous."""
    init, mig = _init_columns("performance_reviews"), _migration_columns()
    assert len(init) >= 15, f"only parsed {len(init)} columns from init_db_fixed.py"
    assert len(mig) >= 8, f"only parsed {len(mig)} columns from the migration"
    assert "ai_decision" in init and "ai_decision" in mig


def test_every_added_column_matches_the_initialiser_type():
    init = _init_columns("performance_reviews")
    mismatched = []
    for col, typ in _migration_columns().items():
        want = init.get(col)
        assert want, (
            f"the migration adds {col}, which init_db_fixed.py does not define — "
            "the two provisioning paths would now produce different tables")
        if want != typ:
            mismatched.append(f"{col}: migration={typ} init={want}")
    assert mismatched == [], (
        "these columns have different types depending on how the database was "
        "provisioned:\n  " + "\n  ".join(mismatched))
