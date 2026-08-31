"""
Every column the code writes exists somewhere that creates it.

WHY THIS IS A TEST
POST /api/employees/{id}/terminate and /rehire answered 500:

    UndefinedColumn: column "termination_date" of relation "employees"

Terminating an employee is not an edge case; it is one of the two or three
things an HR system must do, and it had never worked. Six statements read or
wrote termination_date and two wrote termination_reason. Neither column existed
in the models, in any migration, or in the database.

It survived because nothing checks the two against each other. The route needs
an employee id, so the parameterless sweep could not reach it; the models are a
Python file and the migrations are SQL, so nobody diffs them; and the failure
only appears when someone actually terminates somebody.

The fix needed BOTH a migration and a model change. A migration alone leaves a
deployment provisioned by create_all rebuilding employees without the columns --
the two-provisioning-paths problem in BETA_READINESS blocker #6, which is
exactly how a fix like this quietly comes undone.

This test reads what the code writes and checks it against every schema source
in the package. It needs no database, so it cannot skip.
"""
from __future__ import annotations

import pathlib
import re

from sqlalchemy import MetaData

from app.db import models

APP = pathlib.Path("app")
MIGRATIONS = pathlib.Path("migrations")

# Tables written by raw SQL whose definition lives outside this package (or in
# init_db_fixed.py, which is not a schema source we parse). Their columns cannot
# be checked here; test_router_tables_exist.py tracks the tables themselves.
UNCHECKABLE = {
    "ai_decisions", "ai_memories", "expo_push_tokens", "screening_criteria",
    "investigation_cases", "integration_connections", "policy_rules",
    "policy_executions", "documents", "benefit_enrollment_windows",
}


def _model_columns() -> dict[str, set[str]]:
    md = next(
        o.metadata for _, o in vars(models).items()
        if hasattr(o, "metadata") and isinstance(getattr(o, "metadata", None), MetaData)
    )
    out: dict[str, set[str]] = {}
    for name, table in md.tables.items():
        out.setdefault(name.split(".")[-1], set()).update(c.name for c in table.columns)
    return out


def _migration_columns() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    if not MIGRATIONS.exists():
        return out
    for path in MIGRATIONS.glob("*.sql"):
        sql = path.read_text()
        for m in re.finditer(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?(\w+)\s*\((.*?)\n\s*\)\s*;",
                             sql, re.IGNORECASE | re.DOTALL):
            # Compare the first token EXACTLY, not by prefix. Matching a
            # prefix skipped the columns literally named "checked" and
            # "checklist" as if they were CHECK constraints, and this test
            # then reported both as writes to columns nobody creates. A
            # detector's own false positives are indistinguishable from
            # findings until someone checks them by hand.
            keywords = {"primary", "unique", "foreign", "constraint", "check", "exclude", "like"}
            cols = set()
            for line in m.group(2).splitlines():
                tokens = line.strip().split()
                if not tokens or line.strip().startswith("--"):
                    continue
                first = tokens[0].strip('"').lower()
                if first in keywords:
                    continue
                cols.add(tokens[0].strip('"'))
            out.setdefault(m.group(1).lower(), set()).update(c for c in cols if c.isidentifier())
        for m in re.finditer(r"alter\s+table\s+(?:public\.)?(\w+)(.*?);", sql, re.IGNORECASE | re.DOTALL):
            for col in re.finditer(r"add\s+column\s+(?:if\s+not\s+exists\s+)?(\w+)", m.group(2), re.IGNORECASE):
                out.setdefault(m.group(1).lower(), set()).add(col.group(1))
    return out


def _runtime_guarded() -> set[tuple[str, str]]:
    """Columns a handler checks for before using, e.g.

        if await column_exists(db, "policies", "scope"):

    That is a deliberate optional-schema pattern, not a latent crash, and a
    static scan cannot see it. Flagging it would be a false positive, and false
    positives are how a guard like this gets switched off.
    """
    out: set[tuple[str, str]] = set()
    for path in APP.rglob("*.py"):
        for m in re.finditer(r'column_exists\(\s*\w+\s*,\s*"(\w+)"\s*,\s*"(\w+)"', path.read_text()):
            out.add((m.group(1).lower(), m.group(2).lower()))
    return out


def _written_columns() -> dict[str, set[tuple[str, str]]]:
    """table -> {(column, "file:line")} for INSERT column lists and UPDATE SET."""
    out: dict[str, set[tuple[str, str]]] = {}
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text()
        for m in re.finditer(r"insert\s+into\s+(?:public\.)?(\w+)\s*\(([^)]*)\)", text, re.IGNORECASE | re.DOTALL):
            line = text[:m.start()].count("\n") + 1
            for c in m.group(2).replace("\n", " ").split(","):
                c = c.strip().strip('"')
                if c.isidentifier():
                    out.setdefault(m.group(1).lower(), set()).add((c.lower(), f"{path}:{line}"))
        for m in re.finditer(r"update\s+(?:public\.)?(\w+)\s+set\s+(.*?)(?:\bwhere\b|\"\"\")", text,
                             re.IGNORECASE | re.DOTALL):
            line = text[:m.start()].count("\n") + 1
            for assign in m.group(2).split(","):
                name = assign.strip().split("=")[0].strip().strip('"')
                if name.isidentifier():
                    out.setdefault(m.group(1).lower(), set()).add((name.lower(), f"{path}:{line}"))
    return out


def test_no_statement_writes_a_column_nothing_creates():
    known = _model_columns()
    for table, cols in _migration_columns().items():
        known.setdefault(table, set()).update(cols)

    guarded = _runtime_guarded()

    offenders = []
    for table, written in sorted(_written_columns().items()):
        if table in UNCHECKABLE or table not in known:
            continue
        for col, where in sorted(written):
            if col in known[table] or (table, col) in guarded:
                continue
            offenders.append(f"{where}  {table}.{col}")

    assert offenders == [], (
        "these statements write columns that no model and no migration create, "
        "so they raise UndefinedColumn the first time they run:\n  "
        + "\n  ".join(offenders)
    )


def test_the_employees_columns_this_was_written_for_are_present():
    """The specific regression. Both schema sources must carry them -- a
    migration alone leaves create_all deployments broken."""
    model = _model_columns()["employees"]
    migration = _migration_columns().get("employees", set())
    for col in ("termination_date", "termination_reason"):
        assert col in model, f"employees.{col} missing from the SQLAlchemy model"
        assert col in migration, f"employees.{col} missing from the migrations"


def test_the_detector_would_have_caught_the_original_defect():
    """MUTATION CONTROL. Remove the columns from what is known and confirm the
    writes are flagged -- otherwise a green result proves nothing."""
    known = {"employees": _model_columns()["employees"] - {"termination_date", "termination_reason"}}
    written = _written_columns()
    missed = [
        f"{table}.{col}"
        for table, cols in written.items() if table in known
        for col, _ in cols if col not in known[table]
    ]
    assert "employees.termination_date" in missed, (
        f"the scan does not see the termination write at all; it found {missed}"
    )


def test_the_detector_reads_real_statements():
    """CONTROL. If the SQL extraction silently found nothing, every assertion
    above passes vacuously."""
    written = _written_columns()
    assert len(written) > 20, f"only found writes to {len(written)} tables; the extraction is broken"
    assert "employees" in written
    assert any(c == "status" for c, _ in written["employees"])
