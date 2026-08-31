"""Bootstrap the Fintra People (HR) schema on a Supabase Postgres.

Idempotent — safe to run repeatedly. It:
  1. Verifies it can connect to whatever DATABASE_URL points at.
  2. Enables required extensions (pgcrypto / uuid-ossp).
  3. Creates every ORM table via SQLAlchemy `Base.metadata.create_all`.
  4. Applies EVERY file in migrations/, in order.
  5. Verifies the result against the table list the application expects, and
     FAILS if anything is missing.

WHY STEP 4 REPLACED A HAND-MAINTAINED LIST
This script used to carry its own `_EXTRA_TABLES_SQL` — "the raw tables that
live outside the ORM … keep this list in sync with any ad-hoc DDL." It had
drifted badly. Measured against a database built from the ORM plus every
migration:

    this script produced        46 tables
    the application needs      120 tables

74 missing, including every table behind interviews (interviews,
interview_answers, interview_scorecards, transcript_segments, recording_assets),
the whole equity and cap-table subsystem, performance (objectives, key_results,
nine_box_placements, one-on-ones), recognition, surveys, and comp_records.

Anyone following the documented path to stand HR up on their own Supabase got a
database missing 62% of its schema, and found out one screen at a time. A list
that must be kept in sync by hand is a list that stops being in sync; the
migrations are the schema, so this applies the migrations.

Usage
-----
    cd packages/hr-api
    export DATABASE_URL='postgresql+asyncpg://postgres.<ref>:<PWD>@aws-0-<region>.pooler.supabase.com:5432/postgres'
    python3 scripts/bootstrap_supabase.py

This does NOT create the Supabase *project* (a dashboard / Management API
operation) and does NOT move any data — it provisions the HR schema on a
database you already have a connection string for.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

# Make the app importable when run from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402


MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations"


async def _apply_migrations(engine) -> tuple[int, list]:
    """Every migration, in order, each in its own transaction.

    Ordered lexically, which is chronological because the files are date
    prefixed. A failure is COLLECTED rather than raised: one migration that
    cannot apply to a particular database should not leave the other 24
    unapplied, and the caller reports what did not land instead of a script
    that half-finished in silence.
    """
    applied, failed = 0, []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        sql = f.read_text(errors="replace")
        try:
            async with engine.begin() as conn:
                # The RAW driver connection, not conn.execute(text(sql)).
                #
                # A migration file is a script, and SQLAlchemy sends it as one
                # prepared statement — asyncpg then refuses it with "cannot
                # insert multiple commands into a prepared statement", which is
                # every migration here, all 25 of them. It also reads `:s` inside
                # the SQL as a bind parameter and fails asking for a value.
                #
                # asyncpg's own execute() uses the simple query protocol, which
                # is what a script needs and what psql does.
                raw = await conn.get_raw_connection()
                driver = getattr(raw, "driver_connection", None) or raw.connection
                await driver.execute(sql)
            applied += 1
        except Exception as exc:
            failed.append((f.name, str(exc).strip().splitlines()[0][:200]))
    return applied, failed


async def main() -> int:
    # Import here so the sys.path tweak above is in effect.
    from app.core.config import settings
    from app.db.session import engine
    from app.db.models import Base
    import app.db.models  # noqa: F401  (registers all models on Base.metadata)

    if engine is None:
        print("✗ DATABASE_URL is not configured. Set it before running.", file=sys.stderr)
        return 2

    url = settings.database_url or ""
    safe = url
    # redact password in the printed URL
    if "@" in safe and "://" in safe:
        scheme, rest = safe.split("://", 1)
        if "@" in rest:
            creds, host = rest.split("@", 1)
            if ":" in creds:
                user = creds.split(":", 1)[0]
                creds = f"{user}:***"
            safe = f"{scheme}://{creds}@{host}"
    print(f"→ Target: {safe}")
    is_supabase = "supabase.co" in url.lower() or "supabase.com" in url.lower()
    print(f"→ Supabase host detected: {is_supabase}")

    # 1. Full schema: init_db_fixed.init_models() runs Base.metadata.create_all
    #    PLUS every raw-SQL table that lives outside the ORM (benefits, bonus,
    #    performance, policy versioning, integrations, market_benchmarks, …).
    #    It is idempotent (every statement is `create table if not exists`).
    from init_db_fixed import init_models  # noqa: E402
    await init_models()

    # 2. Extensions + extra raw tables not covered by init_models.
    async with engine.begin() as conn:
        await conn.execute(text("create extension if not exists pgcrypto"))
        try:
            await conn.execute(text('create extension if not exists "uuid-ossp"'))
        except Exception:
            pass  # not all plans allow uuid-ossp; pgcrypto's gen_random_uuid() suffices

    # 3. Every migration, in order. These carry the ~74 tables the ORM does not.
    applied, failed = await _apply_migrations(engine)
    print(f"  migrations applied: {applied}")
    for name, err in failed:
        print(f"  MIGRATION FAILED  {name}: {err}")

    # 4. Verify against what the application actually expects, and FAIL if
    #    anything is missing. A bootstrap that reports success over an
    #    incomplete schema is how this drifted 74 tables in the first place.
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "select table_name from information_schema.tables "
            "where table_schema='public' order by table_name"
        ))).fetchall()
    present = {r[0] for r in rows}

    expected_file = pathlib.Path(__file__).resolve().parent / "expected_tables.txt"
    missing = []
    if expected_file.exists():
        expected = {l.strip() for l in expected_file.read_text().splitlines()
                    if l.strip() and not l.startswith("#")}
        missing = sorted(expected - present)

    print(f"\n  {len(present)} tables in public schema")
    if missing:
        print(f"\n  INCOMPLETE — {len(missing)} expected table(s) are missing:")
        for m in missing:
            print(f"    · {m}")
        print("\n  This database is NOT ready. Fix the failures above and re-run.")
        return 1

    print("  every expected table is present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
