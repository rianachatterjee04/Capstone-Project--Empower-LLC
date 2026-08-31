"""
Every table a router or service queries is created by something.

WHY THIS IS A TEST
Probing all 188 parameterless GET routes turned up four server errors, none of
which was visible from the browser:

    GET /api/reviews                    column "ai_decision" does not exist
    GET /api/reviews/cycles             column "opened_at" does not exist
    GET /api/benefits/plans             relation "public.benefit_plans" ...
    GET /api/benefits/optimization-runs relation "public.benefit_optimization_runs" ...
    GET /api/bonuses/pools              relation "public.bonus_pools" ...

Every page degraded to an honest empty state — "No plans yet", "No review cycle
is running yet" — which is exactly what a successful empty response looks like.
Four 500s behind four correct-looking screens.

Those are fixed. This holds the shape: a table referenced in SQL must be
created by a migration, by an ORM model, or by init_db_fixed.py.

WHAT THIS DOES NOT CLAIM. Twenty-nine referenced tables are still created
nowhere. None of them fails a GET today — they sit behind try/except fail-soft
paths or on write endpoints — so they are recorded rather than fabricated. I am
not inventing twenty-nine schemas from the shape of their queries; I did that
once tonight for a single CHECK constraint and got the vocabulary wrong. The
list below is the work, written where the next person will find it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TABLE_REF = re.compile(r"(?:from|into|update|join)\s+public\.([a-z_][a-z0-9_]*)", re.I)
CREATES = re.compile(r"create table (?:if not exists )?(?:public\.)?([a-z_][a-z0-9_]*)", re.I)
TABLENAME = re.compile(r'__tablename__\s*=\s*"([a-z_][a-z0-9_]*)"')

# Referenced in SQL, created by nothing. Every entry is reachable only through
# a fail-soft path or a write endpoint today. Shrinking this list is the work;
# growing it silently is what this test prevents.
KNOWN_UNCREATED = {
    "ai_decisions", "ai_memories", "ai_memory_chunks", "ai_overrides",
    "ats_candidates", "ats_job_postings", "ats_job_screening_criteria",
    "ats_screening_scores", "ats_stage_mappings", "audit_ledger",
    "benefit_preferences", "case_actions", "case_evidence", "case_snapshots",
    "comp_adjustments", "data_exports", "document_versions", "documents",
    "expo_push_tokens", "integration_cursors", "integrations",
    "investigation_actions", "investigation_cases", "investigation_evidence",
    "investigation_witnesses", "org_domains", "reviews", "screening_criteria",
    "users",
}


def _referenced() -> set[str]:
    out: set[str] = set()
    for f in (ROOT / "app").rglob("*.py"):
        src = re.sub(r"(?m)^\s*#.*$", "", f.read_text())
        out |= {m.group(1).lower() for m in TABLE_REF.finditer(src)}
    return out


def _created() -> set[str]:
    out: set[str] = set()
    for p in (ROOT / "migrations").glob("*.sql"):
        out |= {m.lower() for m in CREATES.findall(p.read_text())}
    init = ROOT / "init_db_fixed.py"
    if init.exists():
        out |= {m.lower() for m in CREATES.findall(init.read_text())}
    for f in (ROOT / "app").rglob("*.py"):
        out |= {m.lower() for m in TABLENAME.findall(f.read_text())}
    return out


def test_the_scan_sees_both_sides():
    """CONTROL. Either half coming up short makes the assertions vacuous."""
    ref, made = _referenced(), _created()
    assert len(ref) >= 50, f"only {len(ref)} table references found"
    assert len(made) >= 100, f"only {len(made)} table definitions found"
    # a table known to be referenced and known to be created
    assert "trucking_loads" in ref
    assert "trucking_loads" in made


def test_no_new_table_is_referenced_without_being_created():
    new = sorted(_referenced() - _created() - KNOWN_UNCREATED)
    assert new == [], (
        "these are queried in SQL but created by no migration, no ORM model "
        "and not init_db_fixed.py:\n  " + "\n  ".join(new) +
        "\n\nAn endpoint reaching one of these returns 500, and if the page "
        "degrades to an empty state nobody will see it. Create the table, or "
        "add it to KNOWN_UNCREATED with the reason it is unreachable.")


def test_the_uncreated_list_does_not_go_stale():
    """An entry that gets created, or stops being referenced, must leave."""
    ref, made = _referenced(), _created()
    fixed = sorted(t for t in KNOWN_UNCREATED if t in made)
    gone = sorted(t for t in KNOWN_UNCREATED if t not in ref)
    assert fixed == [], f"these now exist; remove them from KNOWN_UNCREATED: {fixed}"
    assert gone == [], f"these are no longer referenced; remove them: {gone}"


def test_the_four_tables_fixed_tonight_are_created():
    made = _created()
    for t in ("benefit_plans", "benefit_optimization_runs", "bonus_pools",
              "bonus_allocations"):
        assert t in made, f"{t} is missing again; GET would 500"
