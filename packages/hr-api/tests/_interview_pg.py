"""Where the interview tests get their database, and when they may skip.

THE BUG THIS FIXES
The first version skipped when no DSN was set. But `FINTRA_HR_PG_DSN` is set
across most of this repo and points at a database that has the HR schema and
NOT the interview schema. So the tests did not skip -- they ran and produced 26
errors that looked like product failures and were a missing bootstrap.

A test that cannot tell "the schema is absent" from "the code is broken" is not
a usable instrument. So the guard checks for a table, not for a string.

AND IT SAYS SO LOUDLY
The skip reason names the script to run. A silent skip on a security control --
these files include the cross-tenant attacks -- is the failure mode that
matters, so the reason has to make it obvious that coverage was lost rather
than earned.
"""
from __future__ import annotations

import asyncio
import os

#: Prefer the dedicated DSN; fall back to the shared HR one.
DSN = (os.environ.get("FINTRA_INTERVIEW_PG_DSN")
       or os.environ.get("FINTRA_HR_PG_DSN"))

_BOOTSTRAP = "scripts/ephemeral_interview_db.sh"


def _probe(dsn: str) -> bool:
    """Is the interview schema actually present on this database?"""
    try:
        import asyncpg
    except ImportError:      # pragma: no cover
        return False

    # asyncpg takes a libpq URL, not SQLAlchemy's.
    url = dsn.replace("postgresql+asyncpg://", "postgresql://")
    if url.startswith("postgresql:///"):
        url = "postgresql://localhost/" + url[len("postgresql:///"):]

    async def check() -> bool:
        conn = None
        try:
            conn = await asyncpg.connect(url, timeout=5)
            return bool(await conn.fetchval("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='interview_evidence'
            """))
        except Exception:
            return False
        finally:
            if conn is not None:
                await conn.close()

    try:
        return asyncio.run(check())
    except RuntimeError:     # already inside a loop (shouldn't happen at import)
        return False


def skip_reason() -> str | None:
    """None when the tests can run; otherwise why they cannot."""
    if not DSN:
        return (f"needs PostgreSQL. Build one with {_BOOTSTRAP} and export "
                f"FINTRA_INTERVIEW_PG_DSN. A skipped run is not a passing run, "
                f"and these files include the cross-tenant attack suite.")
    if not _probe(DSN):
        return (f"the database at FINTRA_INTERVIEW_PG_DSN/FINTRA_HR_PG_DSN has "
                f"no interview schema. Run {_BOOTSTRAP} — pointing these tests "
                f"at a database without the interview tables loses the "
                f"cross-tenant attack coverage entirely.")
    return None


SKIP_REASON = skip_reason()
AVAILABLE = SKIP_REASON is None
