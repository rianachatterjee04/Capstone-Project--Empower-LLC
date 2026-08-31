"""
Where the shipped sample people appear, and whether the reader is told.

WHY THIS IS A TEST
Six invented people — Avery Chen, Sam Rivera, Jordan Patel, Riley Singh, Morgan
Lee, Emily Stone — are seeded across this codebase so a new tenant is not
looking at an empty product. That is a reasonable thing to ship. What was not
reasonable is what several screens did with them:

  workforce risk    "High-severity workforce risk detected — review today",
                    naming Avery Chen with a compa-ratio and an engagement score
  exec brief        "Top retention concern: Avery Chen", the first line an owner
                    reads in the morning
  pay equity        a 16.2% gender pay gap and a $32,825 remediation budget,
                    under EU Pay Transparency Directive readiness
  workforce graph   "Total workforce 11" for a company with one employee, and a
                    $120,000 salary defaulted onto a real CDL driver
  predictive        "Total employees scored 5", Avery Chen at 80 high risk
  team workspaces   five departments with fixed managers, missions and req counts

The organisation reading all of that has one employee.

This test does not require the seeds to go. It records which services emit the
sample cohort and whether they mark it, so that:

  * a service that starts emitting them is a visible, deliberate change here;
  * the ones already fixed cannot quietly lose their provenance markers.

If you are here because this failed, the question is not "how do I make it
pass". It is: does this screen tell the reader these are not their people?
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

SAMPLE_NAMES = ("Avery Chen", "Sam Rivera", "Jordan Patel", "Riley Singh",
                "Morgan Lee", "Emily Stone")

# Vocabulary that tells a caller the data is illustrative.
#
# "source" and "source=" are NOT here, and that is the point. They matched
# three services that mean something else entirely by the word:
#
#   people_crm_service   source="LinkedIn inbound"      — recruiting channel
#   org_graph_service    GraphEdge(source=n.manager_id) — an edge endpoint
#   tasks_service        source="performance"           — originating module
#
# All three were being reported as declaring provenance while declaring none.
# A guard that says "fixed" about something unfixed is worse than one that says
# nothing, because it stops anyone looking.
PROVENANCE = ("is_sample", "is_template", "sample_cohort", "sample_workforce",
              "sample_profile", "provenance", "template_note", "illustrative",
              "employee_record", "sample people", "all_sample")

# Services that emit a sample name AND declare it. Losing a marker here is a
# regression, so the set is pinned rather than merely counted.
DECLARED = {
    "attrition.py",
    "calendar_service.py",
    "cpo_service.py",
    "goals_service.py",
    "manager_brief_service.py",
    "notifications_service.py",
    "pay_equity_service.py",
    "people_crm_service.py",
    "recognition_service.py",
    "team_workspace_service.py",
    "workforce_finance_service.py",
    "workforce_graph_service.py",
    "digital_twin.py",
    "digital_twin_service.py",
    "org_design_service.py",
    "org_graph_service.py",
    "public_profile_service.py",
    "talent_marketplace_service.py",
    "tasks_service.py",
    "workforce_risk_service.py",
}

# Services that emit a sample name and do NOT declare it. Every one is a screen
# somewhere that may be presenting an invented person as the reader's own. They
# are recorded, not excused; shrinking this set is the work.
#
# It is now empty. The eight that were here all declare:
#
#   attrition.py                  each prediction carries is_sample; an attrition
#                                 score attached to a NAME is a claim about that person
#   digital_twin.py               every directory card marked
#   digital_twin_service.py       DigitalTwin.is_sample is True whenever no employee
#                                 row was found and the twin came from a seed
#   org_design_service.py         every person in the fallback org chart marked
#   org_graph_service.py          GraphNode.is_sample propagates from that chart, so
#                                 the attrition band and succession rating drawn on a
#                                 node are attributable
#   public_profile_service.py     each seeded profile marked -- a bio and a
#                                 "currently working on" list reads as someone's own words
#   talent_marketplace_service.py every pooled candidate marked
#   tasks_service.py              Task.is_sample is True for the seeded queue, whose
#                                 items name invented people as owner AND subject
UNDECLARED: set[str] = set()
# approvals_service.py is deliberately absent: its two synthetic approvals were
# deleted, and the names now survive only in the comment recording that. Once
# comments stopped counting, it left this list on its own — which is the
# staleness check below doing its job.


def _code(src: str) -> str:
    """Source with docstrings and comments removed.

    Provenance has to be in the CODE. Checking raw source let a service satisfy
    this guard with a comment that merely mentions the word "illustrative" —
    I proved it by stripping the real markers out of workforce_risk_service and
    watching all four tests still pass, because the explanatory comment was
    left behind. A guard a comment can satisfy is not a guard.
    """
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"(?m)^\s*#.*$", "", src)


def _emitters() -> dict[str, bool]:
    """{filename: declares_provenance} for every file mentioning a sample name."""
    out = {}
    for f in sorted(APP.rglob("*.py")):
        if "test" in f.name:
            continue
        code = _code(f.read_text())
        if not any(n in code for n in SAMPLE_NAMES):
            continue
        out[f.name] = any(k in code for k in PROVENANCE)
    return out


def test_the_scan_finds_the_sample_cohort():
    """CONTROL. If the names change, this file is silently checking nothing."""
    found = _emitters()
    assert len(found) >= 15, (
        f"only {len(found)} files mention the sample cohort — the names in "
        "SAMPLE_NAMES are probably stale")
    assert "workforce_risk_service.py" in found


def test_no_new_service_emits_sample_people_undeclared():
    found = _emitters()
    undeclared = {n for n, declared in found.items() if not declared}
    new = sorted(undeclared - UNDECLARED)
    assert new == [], (
        "these emit the shipped sample people without saying so anywhere:\n  "
        + "\n  ".join(new) +
        "\n\nIf a screen shows them, tell the reader they are not their "
        "employees — see workforce_risk_service or pay_equity_service for the "
        "shape. If it does not, add it to UNDECLARED with that note.")


def test_the_declared_services_keep_their_provenance():
    found = _emitters()
    lost = sorted(n for n in DECLARED if n in found and not found[n])
    assert lost == [], (
        "these used to tell the reader the data was illustrative and no longer "
        f"do: {lost}")


def test_the_undeclared_list_does_not_grow_stale():
    """An entry that stops emitting sample names should leave the list."""
    found = _emitters()
    gone = sorted(n for n in UNDECLARED if n not in found)
    assert gone == [], (
        f"these no longer emit sample people; remove them from UNDECLARED: {gone}")
