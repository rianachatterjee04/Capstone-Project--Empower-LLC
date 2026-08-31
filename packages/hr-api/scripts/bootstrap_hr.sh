#!/usr/bin/env bash
# ============================================================================
# HR schema bootstrap — idempotent, single command.
#
# Stands up the COMPLETE Foundry People (hr-api) schema on a fresh Postgres and
# seeds demo data:
#   1. init_db_fixed.py         — ORM Base.metadata.create_all + the raw-SQL
#                                 tables that mirror the migrations
#   2. migrations/*.sql         — every dated migration, in order (idempotent;
#                                 resolves the performance_reviews.rating +
#                                 unique-constraint drift, and adds cfo_scenarios
#                                 + org_security_settings)
#   3. scripts/seed_hr_demo.sql — org + 10 employees + job posting + candidate
#                                 + performance/comp records
#
# Everything is idempotent — safe to re-run.
#
# Env:
#   DATABASE_URL  SQLAlchemy asyncpg URL used by init_db_fixed.py, e.g.
#                 postgresql+asyncpg://<user>@localhost:5432/fintra_hr
#                 (read from packages/hr-api/.env if not exported)
#   PSQL_URL      libpq URL for psql (defaults to DATABASE_URL with the
#                 +asyncpg driver suffix stripped)
#   PYTHON        python interpreter (defaults to ./.venv/bin/python or python3)
# ============================================================================
set -euo pipefail

API_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$API_DIR"

# Resolve DATABASE_URL from env or .env
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"
fi
: "${DATABASE_URL:?set DATABASE_URL (postgresql+asyncpg://user@host:5432/db)}"
export DATABASE_URL

# psql (libpq) URL: strip the +asyncpg driver marker
PSQL_URL="${PSQL_URL:-$(printf '%s' "$DATABASE_URL" | sed 's/+asyncpg//')}"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x ".venv/bin/python" ]; then PYTHON=".venv/bin/python"; else PYTHON="python3"; fi
fi

echo ">> [1/3] init_db_fixed.py (create_all + core raw SQL)"
"$PYTHON" init_db_fixed.py

echo ">> [2/3] applying migrations/*.sql in order"
for f in $(ls migrations/*.sql | sort); do
  echo "   -- $(basename "$f")"
  psql "$PSQL_URL" -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null
done

echo ">> [3/3] seeding demo data"
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -q -f scripts/seed_hr_demo.sql >/dev/null

TBLS=$(psql "$PSQL_URL" -Atc "select count(*) from information_schema.tables where table_schema='public';")
EMPS=$(psql "$PSQL_URL" -Atc "select count(*) from employees;")
echo ">> HR bootstrap complete. public tables=$TBLS, employees=$EMPS"
