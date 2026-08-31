"""
A pay gap is a regulatory claim, so the analysis says whose pay it analysed.

WHY THIS IS A TEST
/app/pay-equity rendered, under a header about EU Pay Transparency Directive
readiness:

    Headcount analysed        16
    Female vs Male            raw gap 16.2%, adjusted gap 8.8%, over threshold
    Flagged categories        5
    Remediation budget        $32,825

for an organisation with one employee. Every number came from the sixteen-person
cohort in _seed() — Avery Chen, Riya Kapoor, Mei Lin and the rest — which the
service loads for any org that has not supplied its own.

A fabricated gender pay gap is the most legally loaded thing this product can
put on a screen. The arithmetic is sound and worth demonstrating; the
implication that it describes the reader's company is what cannot stand.
"""
from __future__ import annotations

from app.services import pay_equity_service as PE

ORG = "test-pay-equity-cohort"
OWN = "test-pay-equity-own"


def test_a_seeded_org_is_told_the_cohort_is_a_sample():
    out = PE.org_analysis(ORG)
    cohort = out.get("cohort")
    assert cohort, "the analysis does not say whose pay it analysed"
    assert cohort["is_sample"] is True
    assert cohort["source"] == "sample_cohort"
    assert "not on your employees" in cohort["note"]
    assert cohort["needs"], "does not say what real data it would need"


def test_the_headline_numbers_are_the_sample_cohort():
    """The banner has to be attached to the numbers it is about."""
    out = PE.org_analysis(ORG)
    assert out["headcount"] == len(PE.list_employees(ORG))
    assert out["headcount"] > 1, (
        "the sample cohort is gone; this test no longer exercises the case that "
        "produced a 16.2% gap for a one-employee company")


def test_real_employees_are_not_labelled_a_sample():
    """CONTROL. The marking must not survive the org supplying its own people.

    A disclaimer that never clears is as misleading as one that never appears:
    it teaches the reader to ignore it, right up to the analysis that is real.

    The org is SEEDED FIRST and then given real employees, because that is the
    order it happens in: somebody opens the page, sees the worked example, and
    then loads their own compensation records. My first version of this test
    used a fresh org, so set_employees ran before anything seeded it — and it
    passed with the flag-clearing line deleted, proving nothing.
    """
    PE.org_analysis(OWN)                      # seeds the sample cohort
    assert PE.uses_sample_cohort(OWN) is True

    own = [
        PE.PEEmployee(id="a", name="A", salary=100000.0, gender="female",
                      level="L4", job_family="Engineering", location="SF",
                      tenure_years=3.0),
        PE.PEEmployee(id="b", name="B", salary=120000.0, gender="male",
                      level="L4", job_family="Engineering", location="SF",
                      tenure_years=3.0),
    ]
    PE.set_employees(OWN, own)
    out = PE.org_analysis(OWN)
    assert out["cohort"]["is_sample"] is False
    assert out["cohort"]["source"] == "employee_records"
    assert out["cohort"]["needs"] == []
    assert out["headcount"] == 2
