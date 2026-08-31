#!/usr/bin/env bash
# Build the whole demo, in the order the demo is given, then check it.
#
# WHY ONE SCRIPT
# The four seeders have to run in a particular order -- the trucking journey
# clears the org, the brokered journey adds to it, the commercial loop attaches
# to whichever account already has freight -- and getting that order wrong
# produced a board of zeros, a loop attributing against an account with no
# loads, and an interview whose recording belonged to a different org. Each of
# those looked like a broken product rather than a seeding mistake, which is
# the expensive kind of demo failure.
#
# It also VERIFIES. A seed script that exits 0 having written nothing is worse
# than one that fails, so the last step reads the API back and refuses to
# report success on an empty board.
#
#   ./scripts/seed_demo.sh                    # into the app's default org
#   ./scripts/seed_demo.sh --db fintra_iv_demo --org <uuid>
set -euo pipefail

DB="fintra_iv_demo"
ORG="11111111-1111-1111-1111-111111111111"
API="${FINTRA_API:-http://localhost:8000}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db)  DB="$2"; shift 2 ;;
    --org) ORG="$2"; shift 2 ;;
    --api) API="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

cd "$HERE"
export FINTRA_INTERVIEW_PG_DSN="postgresql+asyncpg://localhost/${DB}"
export SUPABASE_URL="${SUPABASE_URL:-https://dummy.supabase.co}"
export SUPABASE_KEY="${SUPABASE_KEY:-dummy}"

step() { printf "\n\033[1m%s\033[0m\n" "$*"; }
fail() { printf "\n  REFUSED: %s\n" "$*" >&2; exit 1; }

if ! psql -d "$DB" -c 'SELECT 1' >/dev/null 2>&1; then
  fail "cannot reach the database '$DB'. Build one with
           ./scripts/ephemeral_interview_db.sh $DB"
fi

ORG_NAME=$(psql -d "$DB" -t -A -c "SELECT name FROM public.orgs WHERE id='$ORG'" || true)

# CREATE IT RATHER THAN REFUSE. This check ran BEFORE step 1, and step 1 is what
# creates the organisation -- so on a brand new database the one-command demo
# could never run at all. It stopped with "no organisation ... seed it first",
# which is advice to do by hand the thing the next line was about to do.
#
# The guard's intent is right and is kept: never seed into an org the web app
# will not open. Creating exactly that org satisfies it. The name carries the
# DEMO prefix the seeders require, so this cannot quietly become a real
# organisation.
if [[ -z "$ORG_NAME" ]]; then
  ORG_NAME="DEMO — Northwind Robotics"
  if psql -d "$DB" -q -c "INSERT INTO public.orgs (id,name) VALUES ('$ORG', '$ORG_NAME')" 2>/dev/null; then
    echo "  created the demo organisation $ORG on '$DB'"
  else
    ORG_NAME=""
  fi
fi

if [[ -z "$ORG_NAME" ]]; then
  fail "no organisation $ORG on '$DB' and it could not be created. The web app opens that org by default,
           so seeding anywhere else produces a demo nobody can see."
fi
echo "seeding '$ORG_NAME' ($ORG) on $DB"

step "1/5  HR — candidates, interviews, scorecards"
"$PY" scripts/seed_interview_demo.py >/dev/null

step "2/5  Trucking — the asset journey (clears this org's freight first)"
"$PY" scripts/demo_trucking_journey.py --org "$ORG" >/dev/null

step "3/5  Brokerage — carrier sourcing through settlement"
"$PY" scripts/demo_brokered_journey.py --org "$ORG" >/dev/null

step "4/5  Recording — the demo media, so the debrief's click has somewhere to go"
"$PY" scripts/attach_demo_media.py --org "$ORG"

step "5/5  Growth — the commercial loop, attached to the account with freight"
# Falls back to the committed SYNTHETIC artifact so the loop is in the
# one-command demo. Without it this step printed "skipped -- the Growth page
# will be empty, which is the honest state", and an empty page is an honest
# non-demo: the Market -> Growth -> Marketing -> customer -> load -> margin
# story is the entire commercial argument and could not be shown from a clean
# checkout at all. The fixture names no real business and says so on every row;
# its RIGHTS semantics are real, which is the part that has to be.
ARTIFACT="${FINTRA_OPPORTUNITY_ARTIFACT:-$HERE/demo/opportunity.sample.json}"
if [[ -n "$ARTIFACT" && -f "$ARTIFACT" ]]; then
  FINTRA_DEMO_ORG_NAME="$ORG_NAME" \
    "$PY" scripts/demo_commercial_loop.py --artifact "$ARTIFACT" >/dev/null
else
  echo "  skipped — set FINTRA_OPPORTUNITY_ARTIFACT to a stage-1 scan artifact."
  echo "  The Growth page will be empty, which is the honest state."
fi

# ---------------------------------------------------------------------------
# Verify. A seed that wrote nothing must not report success.
# ---------------------------------------------------------------------------
step "Checking what actually landed"
psql -d "$DB" -t -A -F' | ' <<SQL
SELECT 'loads',        count(*) FROM public.trucking_loads       WHERE org_id='$ORG'
UNION ALL SELECT 'invoices',     count(*) FROM public.trucking_invoices    WHERE org_id='$ORG'
UNION ALL SELECT 'settlements',  count(*) FROM public.trucking_settlements WHERE org_id='$ORG'
UNION ALL SELECT 'rate confirmations', count(*) FROM public.trucking_rate_confirmations WHERE org_id='$ORG'
UNION ALL SELECT 'interviews',   count(*) FROM public.interviews           WHERE org_id='$ORG'
UNION ALL SELECT 'scorecards',   count(*) FROM public.interview_scorecards WHERE org_id='$ORG'
UNION ALL SELECT 'prospects',    count(*) FROM public.commercial_prospects WHERE org_id='$ORG'
UNION ALL SELECT 'recording parts', count(*) FROM public.recording_assets  WHERE org_id='$ORG';
SQL

LOADS=$(psql -d "$DB" -t -A -c "SELECT count(*) FROM public.trucking_loads WHERE org_id='$ORG'")
IVS=$(psql -d "$DB" -t -A -c "SELECT count(*) FROM public.interviews WHERE org_id='$ORG'")
[[ "$LOADS" -gt 0 ]] || fail "no loads were seeded; the trucking board would be empty"
[[ "$IVS"   -gt 0 ]] || fail "no interviews were seeded; the recruiter page would be empty"

if curl -sf -o /dev/null "$API/health" 2>/dev/null; then
  TOKEN="dev:${ORG}:owner:demo@local.test:22222222-2222-2222-2222-222222222222"
  TILES=$(curl -s -H "Authorization: Bearer $TOKEN" "$API/api/trucking/today" \
          | "$PY" -c 'import json,sys
b = json.load(sys.stdin)
print(sum(1 for t in b.get("operations", []) + b.get("money", []) if t["value"]))' 2>/dev/null || echo 0)
  echo
  echo "  the Today board serves $TILES non-zero tiles"
  [[ "$TILES" -gt 0 ]] || fail "the API is up and every tile is zero"
else
  echo
  echo "  (the API is not running at $API, so the board was not checked)"
fi

cat <<'NEXT'

  READY. The five-minute path:

    /app/trucking            Today — every number opens
      click Exceptions       the load that needs a call
      open that load         rate confirmation, POD, both sides of detention,
                             margin graded by its weakest cost
    /app/commercial          the loop: spend -> customer -> freight -> verdict
    /app/recruiting          the interview, then Review
      click any assessment   the recording seeks to that moment

  The demo recording is SYNTHETIC: real MediaRecorder output from a canvas, no
  camera and no person. Every step after getUserMedia is the same code a live
  capture takes -- the recorder, the container, the upload, the duration
  repair, the storage, the range serving, the player. getUserMedia itself is
  the one link it does not exercise.

  Everything is DEMO / SYNTHETIC. Nothing is corroborated by a bank, a GL, an
  ELD or a telematics feed, and every screen says so where it matters.
NEXT
