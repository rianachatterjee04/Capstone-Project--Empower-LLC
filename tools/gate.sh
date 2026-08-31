#!/usr/bin/env bash
# THE CANONICAL TEST INVOCATION. Use this everywhere -- locally, in the commit
# gate, and in CI -- so nobody has to invent a pytest command.
#
# It disables exactly one plugin: web3's pytest_ethereum, which raises
# ImportError against the installed eth_typing and aborts collection. It does
# NOT disable plugin autoload, because that also removes pytest-asyncio and
# turns every async test into a fake failure. See docs/TEST_HARNESS_CONTROL.md.
#
# EVERY RUN GETS ITS OWN OUTPUT DIRECTORY.
# An earlier version wrote to fixed paths under /tmp. Two gate runs overlapped,
# interleaved their writes, and produced a summary whose author could not be
# established -- a number nobody could attribute is not evidence, however
# plausible it looks. Run directories are stamped and never reused.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
RUN_DIR="${FINTRA_GATE_DIR:-/tmp/fintra-gate}/${RUN_ID}"
mkdir -p "$RUN_DIR"

PKG="${1:-}"
shift || true
if [ -z "$PKG" ]; then
  echo "usage: tools/gate.sh <package-name|all> [pytest args...]" >&2
  exit 2
fi

# ai-gateway is excluded: tests/test_gateway.py calls sys.exit() at module
# import, which aborts collection for the whole run. Pre-existing.
#
# WHAT ELSE IS NOT HERE, AND WHY. A package missing from this list is not
# tested by anything -- there is no second runner -- so the omissions are
# written down rather than left to be rediscovered:
#
#   growth       IS here now. 278 tests, all passing, never run by this gate.
#   agentfence   281 tests, all passing today (packages/agentfence/backend).
#                Left out only because the product is folded into SentriAI and
#                that is not my call to encode. Adding it is one word.
#   sentri-api   Refuses to collect: its own production guard rejects
#                placeholder SECRET_KEY / REFRESH_SECRET_KEY. That guard is
#                correct; gating it needs test secrets in the environment.
#
# `growth` lives at packages/growth/backend rather than packages/growth, so
# run_one takes an optional path below.
# HR-only build: the other packages are not part of this repository.
ALL_PKGS="hr-api shared-py"

# DATABASE-ENFORCED CONTROLS MUST NOT SILENTLY SKIP.
# The payroll single-economic-effect control is a PostgreSQL partial unique
# index. Without a DSN its 50 tests skip and the gate reports green over a
# tree whose most important control was never exercised. A skip is not a pass,
# and a gate that cannot see its own blind spot will certify one.
if [ -z "${FINTRA_PAYROLL_PG_ADMIN_DSN:-}" ] \
   && command -v pg_isready >/dev/null 2>&1 && pg_isready -q >/dev/null 2>&1; then
  export FINTRA_PAYROLL_PG_ADMIN_DSN="postgresql:///postgres"
fi
if [ -n "${FINTRA_PAYROLL_PG_ADMIN_DSN:-}" ]; then
  echo "  postgres: ${FINTRA_PAYROLL_PG_ADMIN_DSN} (database-enforced controls WILL run)"
else
  echo "  postgres: UNREACHABLE — database-enforced controls will SKIP." >&2
  echo "            This gate is not verifying single-effect ownership." >&2
fi

# THE SAME BLIND SPOT, ONE PACKAGE OVER.
# hr-api has a database-backed suite that skips without a DSN: the interview
# domain (tests/*_pg.py -- includes the cross-tenant media and recording
# attacks), which SQLite cannot stand in for. The gate reported "hr-api
# passed=803" over those tests for as long as they have existed, which is the
# precise failure the payroll block above was written to prevent.
#
# It is provisioned into a THROWAWAY database. Pointing it at the live
# fintra_hr is out of bounds -- these tests INSERT rows, and a suite that
# writes to a real database is a worse problem than a skipped one.
provision_hr_api() {
  command -v pg_isready >/dev/null 2>&1 && pg_isready -q >/dev/null 2>&1 || {
    echo "  hr-api: postgres UNREACHABLE — the interview suite" >&2
    echo "          (including the cross-tenant attacks) will SKIP." >&2
    return 0
  }
  local hr="${REPO_ROOT}/packages/hr-api"

  if [ -z "${FINTRA_INTERVIEW_PG_DSN:-}" ]; then
    # Reuse the database if the schema is already there; rebuilding it on every
    # gate run would drop it out from under a concurrent run.
    if psql -qtAX -d fintra_iv_test -c \
         "SELECT to_regclass('public.recording_assets')" 2>/dev/null \
         | grep -q recording_assets; then
      export FINTRA_INTERVIEW_PG_DSN="postgresql+asyncpg:///fintra_iv_test"
    elif ( cd "$hr" && ./scripts/ephemeral_interview_db.sh ) >/dev/null 2>&1; then
      export FINTRA_INTERVIEW_PG_DSN="postgresql+asyncpg:///fintra_iv_test"
    else
      echo "  hr-api: could not provision the interview database; those" >&2
      echo "          tests will SKIP. Run scripts/ephemeral_interview_db.sh." >&2
    fi
  fi

  # The equity/cap-table database provisioning that used to live here was
  # removed with the cap table itself: this build has no tests that need it,
  # and a gate that provisions a database for a module it does not ship is a
  # standing invitation to reintroduce the module by accident.
}

summarise() {   # $1 = log file -> "passed failed errors skipped"
  local f="$1"
  local last
  last="$(grep -aE '[0-9]+ (passed|failed|error|skipped)|no tests ran' "$f" | tail -1)"
  local p f_ e s
  p="$(printf '%s' "$last" | grep -oE '[0-9]+ passed'  | grep -oE '[0-9]+')"
  f_="$(printf '%s' "$last" | grep -oE '[0-9]+ failed'  | grep -oE '[0-9]+')"
  e="$(printf '%s' "$last" | grep -oE '[0-9]+ error'   | grep -oE '[0-9]+')"
  s="$(printf '%s' "$last" | grep -oE '[0-9]+ skipped' | grep -oE '[0-9]+')"
  echo "${p:-0} ${f_:-0} ${e:-0} ${s:-0}"
}

run_one() {
  local pkg="$1"; shift
  local dir="${REPO_ROOT}/packages/${pkg}"
  # A few packages keep their python under a subdirectory.
  [ -d "${dir}/tests" ] || [ ! -d "${dir}/backend/tests" ] || dir="${dir}/backend"
  [ -d "${dir}/tests" ] || { echo "  ${pkg}: no tests/"; return 0; }
  local log="${RUN_DIR}/${pkg}.log"
  ( cd "$dir" && python3 -m pytest tests \
      -p no:cacheprovider -p no:pytest_ethereum "$@" ) > "$log" 2>&1
  local rc=$?
  read -r p f e s <<< "$(summarise "$log")"
  printf "  %-13s passed=%-6s failed=%-4s errors=%-4s skipped=%-5s exit=%s\n" \
         "$pkg" "$p" "$f" "$e" "$s" "$rc"
  TOT_P=$((TOT_P + p)); TOT_F=$((TOT_F + f + e)); TOT_S=$((TOT_S + s))
  grep -a '^FAILED' "$log" | sed "s|^FAILED |      ${pkg}: |"
  return $rc
}

case " ${PKG} " in
  *" hr-api "*|*" all "*) provision_hr_api ;;
esac
# THE JAVASCRIPT SUITES RAN NOWHERE.
# packages/hr-web-employer has a `test:ui` script -- UI guards that assert a
# control is wired to something, that every nav route resolves, that uploads
# carry credentials, that the click-to-evidence seek arithmetic is right. No
# gate and no CI workflow ever ran it, so those guards only fired when somebody
# typed the command. A guard nobody runs is a comment.
#
# Skipped, loudly, when a suite needs node_modules and they are absent: this is
# a python gate on most machines and an npm install is not its job to perform.
#
# A suite that runs on `node --test` alone needs NOTHING installed, and gating
# those on node_modules kept packages/app — the largest frontend here — outside
# the gate entirely, with no test script at all. Pass a third argument to say
# the suite is node-only and it runs regardless.
#
# That gap had teeth. With nothing installed, `npx tsc --noEmit` in packages/app
# resolves to an unrelated tsc that prints "This is not the tsc command you are
# looking for" and exits 1; grepping its output for the file under test finds
# nothing, which reads exactly like a clean type check. A planted type error
# went uncaught, which is how the false green was found.
run_js() {
  local pkg="$1" script="$2" node_only="${3:-}"
  local dir="${REPO_ROOT}/packages/${pkg}"
  [ -f "${dir}/package.json" ] || return 0
  if [ ! -d "${dir}/node_modules" ] && [ -z "$node_only" ]; then
    printf "  %-13s SKIPPED — no node_modules (npm install in packages/%s)\n" \
           "$pkg" "$pkg" >&2
    return 0
  fi
  local log="${RUN_DIR}/${pkg}-js.log"
  ( cd "$dir" && npm run --silent "$script" ) > "$log" 2>&1
  local rc=$? p f
  p="$(grep -aoE '^# pass [0-9]+' "$log" | grep -oE '[0-9]+' | tail -1)"
  f="$(grep -aoE '^# fail [0-9]+' "$log" | grep -oE '[0-9]+' | tail -1)"
  printf "  %-13s passed=%-6s failed=%-4s errors=%-4s skipped=%-5s exit=%s\n" \
         "${pkg}(js)" "${p:-?}" "${f:-?}" "0" "0" "$rc"
  TOT_P=$((TOT_P + ${p:-0})); TOT_F=$((TOT_F + ${f:-0}))
  grep -a '^not ok' "$log" | sed "s|^|      ${pkg}: |" | head -20
  return $rc
}

# Compile the Next.js frontends.
#
# WHY THIS EXISTS
# The gate reported 1337 passed / 0 failed while the employee app returned HTTP
# 500 on its compensation page and the employer app could not compile its audit
# page -- both importing a module that had been deleted. No Python test compiles
# TypeScript, and the employer's node --test suite reads source as text rather
# than type-checking it, so an entire broken frontend sat behind a green gate.
#
# The local ./node_modules/.bin/tsc is invoked deliberately: a bare `tsc` on
# PATH resolved to an unrelated binary that printed a message and exited 1, and
# earlier greps for "error TS" found nothing in its output and read that as
# clean. Exit status is what is trusted here, not the absence of matched lines.
run_typecheck() {
  local pkg="$1"
  local dir="${REPO_ROOT}/packages/${pkg}"
  [ -f "${dir}/package.json" ] || return 0
  if [ ! -x "${dir}/node_modules/.bin/tsc" ]; then
    printf "  %-13s SKIPPED — no local tsc (npm install in packages/%s)\n" \
           "${pkg}(tsc)" "$pkg" >&2
    return 0
  fi
  local log="${RUN_DIR}/${pkg}-tsc.log"
  ( cd "$dir" && ./node_modules/.bin/tsc --noEmit ) > "$log" 2>&1
  local rc=$? n
  n="$(grep -ac 'error TS' "$log" || true)"
  printf "  %-13s type-errors=%-4s exit=%s\n" "${pkg}(tsc)" "${n:-0}" "$rc"
  [ "$rc" -ne 0 ] && TOT_F=$((TOT_F + ${n:-1}))
  grep -a 'error TS' "$log" | sed "s|^|      ${pkg}: |" | head -20
  return $rc
}

# The storage-safety guard.
#
# WHY IT IS RUN HERE
# This guard existed, passed, and was wired into nothing -- no gate step, no
# hook, no CI job. A security control that never runs is indistinguishable from
# one that was never written, except that its presence in the tree suggests
# coverage that does not exist.
run_storage_guard() {
  local log="${RUN_DIR}/storage-safety.log"
  ( cd "$REPO_ROOT" && python3 scripts/check_storage_safety.py ) > "$log" 2>&1
  local rc=$?
  printf "  %-13s exit=%s  %s\n" "storage-guard" "$rc" "$(tail -1 "$log" | cut -c1-70)"
  [ "$rc" -ne 0 ] && { TOT_F=$((TOT_F + 1)); sed 's|^|      |' "$log" | head -15; }
  return $rc
}

TOT_P=0; TOT_F=0; TOT_S=0
echo "run: ${RUN_DIR}"
echo "────────────────────────────────────────────────────────────────"
status=0
if [ "$PKG" = "all" ]; then
  for p in $ALL_PKGS; do run_one "$p" "$@" || status=1; done
  run_js hr-web-employer test:ui || status=1
  run_typecheck hr-web-employer || status=1
  run_typecheck hr-web-employee || status=1
  run_storage_guard || status=1
else
  case "$PKG" in
    hr-web-employer) run_js hr-web-employer test:ui || status=1
                     run_typecheck hr-web-employer || status=1 ;;
    hr-web-employee) run_typecheck hr-web-employee || status=1 ;;
    *)               run_one "$PKG" "$@" || status=1 ;;
  esac
fi
echo "────────────────────────────────────────────────────────────────"
printf "  TOTAL passed=%s failed+errors=%s skipped=%s\n" "$TOT_P" "$TOT_F" "$TOT_S"
echo "  logs: ${RUN_DIR}"
exit $status
