"""
The documented way to stand HR up on your own Supabase produces the whole
schema.

WHY THIS IS A TEST
scripts/bootstrap_supabase.py is what a team is told to run to put HR on their
own Supabase project. It carried its own `_EXTRA_TABLES_SQL` — "the raw tables
that live outside the ORM … keep this list in sync with any ad-hoc DDL" — and
it had stopped being in sync. Measured against a database built from the ORM
plus every migration:

    the bootstrap produced      46 tables
    the application needs      120 tables

74 missing: every table behind interviews (interviews, interview_answers,
interview_scorecards, transcript_segments, recording_assets), the whole equity
and cap-table subsystem, performance (objectives, key_results,
nine_box_placements, one-on-ones), recognition, surveys, and comp_records.

Anyone following the documented path got a database missing 62% of its schema
and discovered it one broken screen at a time — the worst way to find out,
because each symptom looks like a different bug.

A list kept in sync by hand is a list that stops being in sync. The migrations
ARE the schema, so the bootstrap applies the migrations, and this test holds the
expected-table list against what the migrations actually create.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest

HR_ROOT = pathlib.Path(__file__).resolve().parents[1]
BOOTSTRAP = HR_ROOT / "scripts" / "bootstrap_supabase.py"
EXPECTED = HR_ROOT / "scripts" / "expected_tables.txt"
MIGRATIONS = HR_ROOT / "migrations"


def _strip_sql_comments(sql: str) -> str:
    """SQL with -- line comments and /* */ blocks removed.

    Scanning raw text for CREATE TABLE matched the words following "create
    table" inside explanatory comments, so a migration that says "...the create
    table above means..." reported tables called `above` and `means`. A guard
    that reads its own prose is the same mistake as one that fires on it.
    """
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return "\n".join(l.split("--")[0] for l in sql.splitlines())


def _tables_created_by_migrations() -> set:
    out = set()
    for f in sorted(MIGRATIONS.glob("*.sql")):
        body = _strip_sql_comments(f.read_text(errors="replace"))
        for m in re.finditer(
                r"create\s+table\s+(?:if\s+not\s+exists\s+)?"
                r"(?:public\.)?([a-z_][a-z0-9_]*)", body, re.I):
            out.add(m.group(1).lower())
    return out


def _expected() -> set:
    return {l.strip() for l in EXPECTED.read_text().splitlines()
            if l.strip() and not l.startswith("#")}


def test_the_expected_list_exists_and_is_not_trivial():
    assert EXPECTED.exists(), f"{EXPECTED} is missing"
    names = _expected()
    assert len(names) > 100, (
        f"only {len(names)} tables recorded; the schema has ~120 and a short "
        f"list is how the old bootstrap reported success over 46"
    )


def test_the_bootstrap_applies_the_migrations():
    src = BOOTSTRAP.read_text()
    assert "_apply_migrations" in src
    assert 'MIGRATIONS.glob("*.sql")' in src, (
        "the bootstrap no longer applies the migration files, so it is back to "
        "creating whatever a hand-maintained list happens to contain"
    )


def test_the_bootstrap_no_longer_carries_its_own_table_list():
    # Read the CODE, not the file: the docstring explains the list it removed,
    # so a substring check on the source matches its own explanation.
    src = BOOTSTRAP.read_text()
    body = "\n".join(l.split("#")[0] for l in src.splitlines())
    body = re.sub(r'"""[\s\S]*?"""', " ", body)
    assert "_EXTRA_TABLES_SQL" not in body, (
        "a second, hand-maintained source of schema truth is back"
    )


def test_the_bootstrap_fails_when_the_schema_is_incomplete():
    """A bootstrap that reports success over a half-built database is how this
    drifted 74 tables without anyone noticing."""
    src = BOOTSTRAP.read_text()
    assert "expected_tables.txt" in src
    assert "return 1" in src, "nothing makes the script exit non-zero"
    assert "NOT ready" in src


def test_it_uses_the_simple_query_protocol_for_scripts():
    """CONTROL for the mechanism. A migration file is a SCRIPT; sending it as a
    prepared statement fails with "cannot insert multiple commands into a
    prepared statement" on every one of them, and SQLAlchemy additionally reads
    `:s` inside the SQL as a bind parameter."""
    src = BOOTSTRAP.read_text()
    assert "get_raw_connection" in src
    assert "driver_connection" in src


def test_every_table_a_migration_creates_is_in_the_expected_list():
    """The drift guard. Add a migration that creates a table and this fails
    until the list is regenerated — which is the moment to notice, rather than
    when a screen 404s on someone else's Supabase.
    """
    created = _tables_created_by_migrations()
    assert created, "no CREATE TABLE found in any migration; the parser broke"

    missing = sorted(created - _expected())
    assert not missing, (
        f"{len(missing)} table(s) are created by a migration but are not in "
        f"scripts/expected_tables.txt: {missing}. Regenerate it — see the "
        f"header of that file — so the bootstrap can verify them."
    )


def test_the_expected_list_does_not_name_tables_nothing_creates():
    """The other direction. A name in the list that nothing builds makes the
    bootstrap fail forever on a correct database."""
    created = _tables_created_by_migrations()

    models = (HR_ROOT / "app" / "db" / "models.py").read_text()
    orm = set(re.findall(r'__tablename__\s*=\s*["\']([a-z_0-9]+)["\']', models))
    init = (HR_ROOT / "init_db_fixed.py").read_text()
    for m in re.finditer(r"create\s+table\s+(?:if\s+not\s+exists\s+)?"
                         r"(?:public\.)?([a-z_][a-z0-9_]*)", init, re.I):
        created.add(m.group(1).lower())

    unknown = sorted(_expected() - created - orm)
    assert not unknown, (
        f"expected_tables.txt names {len(unknown)} table(s) that no migration, "
        f"model or init_db_fixed creates: {unknown}"
    )
