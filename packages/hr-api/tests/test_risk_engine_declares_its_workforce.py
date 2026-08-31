"""
The risk engine says whose workforce it scanned.

WHY THIS IS A TEST
/app/risk rendered "Workforce risk score 38/100 — High-severity workforce risk
detected, review today", and named Avery Chen with drivers "Compa-ratio below
0.85 (under-paid vs. band midpoint)", "No raise in 22 months" and "Engagement
score below 0.5".

Avery Chen does not work here. Every layer of the scan reads
_synthetic_workforce() — five invented people with invented compa-ratios,
engagement scores, overtime hours and PTO balances. `db` and `org_id` are
parameters the scan never used to find anybody. The organisation it was
rendering for has one employee, a CDL driver.

Naming a person and asserting they are underpaid and disengaged is the most
specific claim any screen in this product makes. It cannot be about somebody
we invented, and "review today" cannot sit above it.

The engine still runs on the sample cohort — as a worked example it is worth
showing, and it tells a buyer what the layers do. What changed is that it says
so, marks every alert, and lists what it would need to scan the customer's own
people.
"""
from __future__ import annotations

import asyncio

from app.services import workforce_risk_service as R


class _DB:
    """Counts come back as 1; the scan must not use this to find people."""

    async def execute(self, *a, **k):
        class R_:
            def first(self_inner):
                return (1,)
        return R_()


def _scan():
    return asyncio.run(R.scan(_DB(), "11111111-1111-1111-1111-111111111111")).to_dict()


def test_every_alert_says_whose_workforce_it_is_about():
    out = _scan()
    assert out["alerts"], "the scan produced no alerts at all"
    for a in out["alerts"]:
        assert a.get("source") in ("employee_record", "sample_workforce"), (
            f"alert {a['id']!r} about {a['subject']!r} does not say whether that "
            "is a real employee")


def test_the_headline_does_not_urge_action_on_invented_people():
    out = _scan()
    real_high = [a for a in out["alerts"]
                 if a["severity"] == "high" and a["source"] == "employee_record"]
    if not real_high:
        assert "review today" not in out["headline"].lower(), (
            "the headline urges action on findings about people who do not work "
            f"here: {out['headline']!r}")
        assert "sample" in out["headline"].lower()


def test_the_layers_that_read_real_data_are_marked_real():
    """CONTROL. The marking must not be applied to everything indiscriminately.

    My first pass set source="sample_workforce" on every alert. The compliance
    and hiring layers count this organisation's own cases, requisitions and
    candidates — they are real findings, and their subjects are not people at
    all ("1 high-severity case open"). Marking them sample would have hidden
    genuine findings behind a disclaimer, which is its own dishonesty.
    """
    out = _scan()
    real = {a["kind"] for a in out["alerts"] if a["source"] == "employee_record"}
    assert "compliance" in real or "hiring" in real, (
        "no alert is marked as coming from real data, though the compliance and "
        f"hiring layers query the database: {out['alerts']}")


def test_coverage_states_what_was_scanned_and_what_is_missing():
    cov = _scan()["coverage"]
    assert cov["your_employees_scanned"] == 0
    assert cov["sample_people_scanned"] == len(R._synthetic_workforce())
    assert cov["needs"], "does not say what it would take to scan real employees"
    # Substance, not wording: the note must name the people layers, say they
    # ran on illustrative data, and say they did not run on the customer's
    # employees. Pinning an exact sentence broke the moment the sentence was
    # improved, which teaches people to edit the test instead of the note.
    note = cov["note"].lower()
    assert "illustrative" in note
    assert "not on your" in note
    for layer in ("attrition", "burnout", "manager"):
        assert layer in note, f"the note does not say the {layer} layer used sample data"


def test_the_named_people_are_the_sample_cohort():
    """CONTROL. If these names ever come from the database, the marking is wrong."""
    sample_names = {f.name for f in R._synthetic_workforce()}
    for a in _scan()["alerts"]:
        if a["source"] == "sample_workforce":
            assert a["subject"] in sample_names, (
                f"{a['subject']!r} is marked as a sample person but is not in "
                "the sample cohort")
