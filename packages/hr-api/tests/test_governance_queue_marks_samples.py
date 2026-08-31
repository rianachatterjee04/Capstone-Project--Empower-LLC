"""
The governance decision queue does not ask anyone to sign off on a sample.

WHY THIS IS A TEST
/app/governance is described as "Every pending workforce decision awaiting
sign-off ... ranked on one trust scale". Four of its five decisions were:

    Attrition risk — Avery Chen
    Burnout risk — Avery Chen
    Comp Equity risk — Avery Chen
    Manager risk — Morgan Lee

They come straight from the workforce risk engine, whose four people-layers run
on a sample cohort. The queue took the alerts and dropped their source on the
way in, so a decision about somebody who does not work here was ranked, scored
and presented for approval.

This is the same defect as the inbox counting drafts that do not exist, one
step further along: a queue that counts work nobody can sign off teaches people
to stop reading the number, and this queue is the compliance surface.
"""
from __future__ import annotations

import inspect

from app.api.routers import governance as G


def test_the_risk_source_is_carried_into_the_decision():
    src = inspect.getsource(G)
    body = src.split('"""', 2)[-1]
    assert '"is_sample": is_sample' in body, (
        "the decision no longer carries whether its risk alert was about the "
        "sample cohort")
    assert 'a.get("source", "employee_record")' in body, (
        "the source is no longer read off the alert; it was being dropped on "
        "the way into the queue")


def test_a_sample_decision_is_labelled_in_its_title():
    src = inspect.getsource(G)
    body = src.split('"""', 2)[-1]
    assert '" (sample)" if is_sample else ""' in body, (
        "a sample decision's title is indistinguishable from a real one in any "
        "surface that only reads the title")


def test_the_risk_engine_still_supplies_a_source_to_carry():
    """CONTROL. This whole fix depends on the alert having the field."""
    from app.services.workforce_risk_service import RiskAlert
    from dataclasses import fields
    assert "source" in {f.name for f in fields(RiskAlert)}, (
        "RiskAlert lost its source field, so governance has nothing to read "
        "and every decision here silently becomes 'real' again")
