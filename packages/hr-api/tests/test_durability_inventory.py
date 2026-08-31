"""
Which HR services survive a restart, stated as a fact rather than assumed.

WHY THIS IS A TEST
app/services/_hr_persistence.py exists because goals, 1:1s, recognition,
engagement and 9-box calibration "used to be in-process ``_store`` dicts, so
every deploy or restart wiped the data". Five services were moved onto it. The
rest were not, and nothing recorded which is which.

The gap is not theoretical. During a browser walkthrough an interview created
minutes earlier returned 404 because the API process had reloaded — and the
scorecard the recruiter fills in during that interview lives in the same dict.
An HR product whose interview scorecards do not survive a deploy is a fact a
buyer is entitled to hear from us rather than discover.

This test does not demand that everything persist. It pins the CURRENT split so
that:

  * moving a service onto the bridge is a visible, deliberate change here, and
  * adding a NEW memory-only store fails until someone writes it down.

If you are here because this test failed, the question is not "how do I make it
pass" — it is "should this data survive a restart?" If yes, use the bridge like
goals_service does. If no, add it to MEMORY_ONLY with a reason.
"""
from __future__ import annotations

import re
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"

# Services that reach Postgres through the sync->async bridge.
PERSISTED = {
    "calibration_service.py",
    "engagement_service.py",
    "goals_service.py",
    "oneonone_service.py",
    "recognition_service.py",
}

# Services whose state lives only in the API process. The value is why that is
# survivable today — not an excuse, a scope note.
# Services whose state lives only in the API process. The value says what is
# lost when the process restarts — not an excuse, a scope note. Written from
# the services' own descriptions, not guessed.
MEMORY_ONLY = {
    "agent_marketplace_service.py":
        "agent catalog and install state; re-installable from the catalog",
    "automations_service.py":
        "installed automations and run history; re-installable from templates",
    "candidate_integrity_service.py":
        "fraud/deepfake assessment queue; recomputable from candidate records",
    "grow_service.py":
        "career ladders, competency frameworks and growth plans an admin authors "
        "— AUTHORED CONTENT, lost on restart",
    "interview_copilot_service.py":
        "interviews, AI plans, questions and insights — LOST ON RESTART, and the "
        "most user-visible of these: an interview created minutes earlier 404s "
        "after a reload",
    "interview_loop_service.py":
        "panel scheduling and multi-interviewer scorecards, built on copilot "
        "interviews and lost with them",
    "interview_score_review_service.py":
        "explainable-score reviews and human-in-the-loop recourse decisions — "
        "RECOURSE OUTCOMES, lost on restart",
    "interview_scorecard_service.py":
        "competency ratings, notes and evidence chips a recruiter types during "
        "an interview — LOST ON RESTART",
    "interview_transcription_service.py":
        "live transcript buffer; interview-v2 persists its own media and "
        "transcript separately in Postgres",
    "memory_service.py":
        "AI company-memory collections and documents — INGESTED CONTENT, lost "
        "on restart",
    "notifications_service.py":
        "notification feed; regenerated from source events",
    "pay_equity_service.py":
        "analysis output, recomputed from comp records on demand",
    "people_crm_service.py":
        "talent-relationship records and notes a recruiter writes — AUTHORED "
        "CONTENT, lost on restart",
    "public_profile_service.py":
        "public employee profile overrides",
    "rag_service.py":
        "helpdesk knowledge index; rebuilt from its documents",
    "referrals_service.py":
        "referral records and leaderboard — EMPLOYEE SUBMISSIONS, lost on restart",
    "settings_service.py":
        "settings hub overrides",
    "tasks_service.py":
        "workforce execution tasks; goals/1:1s that reference them do persist",
    "wellness_service.py":
        "wellness pulse responses — EMPLOYEE SUBMISSIONS, lost on restart",
}

STORE = re.compile(
    r"^_(?!log\b|lock\b|p\b)[a-z_]+\s*:\s*(?:dict|list|set)\[.*\]\s*=\s*"
    r"(?:\{\s*\}|\[\s*\]|set\(\))",
    re.M)


def _module_level_stores(path: Path) -> bool:
    """True if the module keeps mutable state in a module-level dict."""
    return bool(STORE.search(path.read_text()))


def test_the_scan_finds_stores_at_all():
    """CONTROL. If the pattern rots, every assertion below passes vacuously."""
    found = {p.name for p in SERVICES.glob("*_service.py") if _module_level_stores(p)}
    assert len(found) >= 20, (
        f"only {len(found)} services matched the module-level store pattern: "
        f"{sorted(found)}")
    # A service known to keep one, and one known not to.
    assert "interview_scorecard_service.py" in found
    assert "health_service.py" not in found


def test_no_undeclared_memory_only_service():
    found = {p.name for p in SERVICES.glob("*_service.py") if _module_level_stores(p)}
    # A persisted service may still keep a fallback dict; that is the bridge's
    # fail-soft design, not an undeclared gap.
    undeclared = sorted(found - set(MEMORY_ONLY) - PERSISTED)
    assert undeclared == [], (
        "these services keep state in a module-level dict and are not recorded "
        "as persisted or memory-only:\n  " + "\n  ".join(undeclared) +
        "\n\nDecide which they are. If the data should survive a restart, use "
        "the _hr_persistence bridge as goals_service does; if not, add it to "
        "MEMORY_ONLY with the reason.")


def test_persisted_services_actually_use_the_bridge():
    for name in sorted(PERSISTED):
        src = (SERVICES / name).read_text()
        assert "_hr_persistence" in src, (
            f"{name} is listed as persisted but does not import the bridge")


def _writes_through_the_bridge(name: str) -> bool:
    """Does this service PERSIST its own state, as opposed to reading something?

    Importing _hr_persistence is not the test. people_crm_service imports it to
    look up employee names for a provenance check and stores nothing through
    it — its own contacts are still in a module dict, which is what this
    inventory is about. `tx(` is the write path; `q(` is a read.
    """
    src = (SERVICES / name).read_text()
    return ".tx(" in src


def test_memory_only_services_do_not_quietly_gain_persistence():
    """The inventory is only useful if it is corrected when it stops being true."""
    wrong = [n for n in sorted(MEMORY_ONLY) if _writes_through_the_bridge(n)]
    assert wrong == [], (
        "these are listed as memory-only but now write through the persistence "
        f"bridge — move them to PERSISTED: {wrong}")


def test_the_persisted_services_do_write_through_it():
    """CONTROL. The rule above is only meaningful if `tx(` marks a real writer."""
    not_writing = [n for n in sorted(PERSISTED) if not _writes_through_the_bridge(n)]
    assert not_writing == [], (
        "these are listed as persisted but never write through the bridge, so "
        f"the write-detection is wrong: {not_writing}")
