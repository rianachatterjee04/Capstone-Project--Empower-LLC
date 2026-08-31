#!/usr/bin/env bash
# Build a throwaway database for the interview tests.
#
# ORM create_all first (orgs, job_postings, candidates, employees -- the models
# the interview domain binds to), then the dated migrations. That order matters:
# 20260829_interview_domain.sql has real foreign keys into those tables and will
# refuse to apply without them, which is the correct behaviour.
#
#   ./scripts/ephemeral_interview_db.sh [dbname]
set -euo pipefail
DB="${1:-fintra_iv_test}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

# Terminate anything still connected before dropping. A running API server
# holds a connection, dropdb then fails, `set -e` aborts BEFORE the migrations
# run, and the script prints nothing useful -- which is how a database ended up
# with the interview tables and none of the trucking ones.
psql -d postgres -q -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
  WHERE datname = '$DB' AND pid <> pg_backend_pid()" >/dev/null 2>&1 || true
dropdb --if-exists "$DB"
createdb "$DB"

cd "$HERE"
SUPABASE_URL="${SUPABASE_URL:-https://dummy.supabase.co}" \
SUPABASE_KEY="${SUPABASE_KEY:-dummy}" \
"$PY" - "$DB" <<'PYEOF'
import asyncio, os, sys
sys.path.insert(0, ".")
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.models import Base
# NOTE: app.interview.models is deliberately NOT imported here.
# Importing it would register the interview tables in Base.metadata, and
# create_all would then build them WITHOUT the CHECK constraints -- which the
# ORM does not declare and which are the whole point of the migration
# (INSUFFICIENT_EVIDENCE having no score, an inference needing a confidence,
# a stored recording needing a location). The migration must be what creates
# them. test_interview_schema.py asserts the constraints are present, so this
# ordering mistake fails loudly rather than silently weakening the schema.

def dsn_for(db):
    """A DSN that honours the standard PG* variables.

    This used to be `postgresql+asyncpg:///{db}` -- no host, which asyncpg
    resolves to a UNIX SOCKET. psql and createdb above already honour PGHOST,
    PGPORT, PGUSER and PGPASSWORD, so on any machine where PostgreSQL is
    reached over TCP -- a service container in CI, Docker, a remote dev box --
    the shell half of this script worked and this Python half quietly did not.
    """
    host = os.environ.get("PGHOST")
    if not host:
        return f"postgresql+asyncpg:///{db}"
    user = os.environ.get("PGUSER", "postgres")
    pwd = os.environ.get("PGPASSWORD", "")
    port = os.environ.get("PGPORT", "5432")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql+asyncpg://{auth}{host}:{port}/{db}"


async def main(db):
    e = create_async_engine(dsn_for(db))
    async with e.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    await e.dispose()

asyncio.run(main(sys.argv[1]))
PYEOF

# EVERY dated migration, in order -- not just the two new ones.
#
# Applying only the interview and trucking migrations produced a database that
# served those suites and broke every other hr-api test that needs the equity
# or HR-module schema. In the gate that read as 238 product failures; a
# controlled A/B against a correctly-built database showed 549 passing. One
# database has to serve the whole package, or the gate measures the bootstrap.
for f in $(ls migrations/*.sql | sort); do
  psql -d "$DB" -v ON_ERROR_STOP=1 -q -f "$f" 2>&1 | grep -viE "already exists, skipping|does not exist, skipping" || true
done

# Print the DSN that will actually reach this database, not a socket form that
# only happens to work on a developer laptop.
if [ -n "${PGHOST:-}" ]; then
  _AUTH="${PGUSER:-postgres}"
  [ -n "${PGPASSWORD:-}" ] && _AUTH="${_AUTH}:${PGPASSWORD}"
  _DSN="postgresql+asyncpg://${_AUTH}@${PGHOST}:${PGPORT:-5432}/$DB"
else
  _DSN="postgresql+asyncpg:///$DB"
fi
echo "ready:  FINTRA_INTERVIEW_PG_DSN=$_DSN pytest -q"
