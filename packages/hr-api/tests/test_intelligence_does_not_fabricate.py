"""
The intelligence endpoints report what they measured, or say they cannot.

WHY THIS IS A TEST
app/intelligence/ held two six-line modules of stubs:

    def forecast_headcount(history):          return {"6_month": 120}
    def attrition_risk(employee):             return 0.12
    def detect_pay_compression(employees):    return []
    def simulate_raise(employee_id, percent): return {"risk": "low"}

and the intelligence router imported that module -- not the 119-line
implementation sitting beside it in app/api/routers/intelligence/.

Two consequences, and the second is the serious one.

forecast_headcount was wired to POST /api/intelligence/workforce/forecast. It
ignored the history it was handed and returned 120 for any organisation of any
size. It escaped notice only because the query feeding it selected hire_date
and termination_date, columns employees does not have, so the endpoint 500'd
before it could fabricate. Fixing the column names alone would have turned a
crash into a confident wrong answer for a one-employee company.

detect_pay_compression returned [] for every input. Rendered, that reads "no
pay compression found" -- a clean bill of health on a legal-risk question,
issued by code that never looked at a salary. The detector that does look had
been written and left unimported.

A number with no derivation is worse than no number: in a screenshot or a board
deck it is indistinguishable from a real one.
"""
from __future__ import annotations

import pytest

from app.api.routers.intelligence import compensation as real
from app.api.routers.intelligence import core
from app.intelligence import compensation as stub_comp
from app.intelligence import workforce as stub_workforce


def test_the_router_uses_the_real_detector_not_the_stub():
    assert real.detect_pay_compression is core.compensation.detect_pay_compression, (
        "the intelligence router is importing a compensation module that is not "
        "the implementation in app/api/routers/intelligence/compensation.py"
    )
    assert core.compensation.__name__ == "app.api.routers.intelligence.compensation", (
        f"router wired to {core.compensation.__name__}"
    )


@pytest.mark.parametrize("fn", ["detect_pay_compression", "simulate_raise"])
def test_the_compensation_stub_refuses_instead_of_answering(fn):
    with pytest.raises(NotImplementedError):
        getattr(stub_comp, fn)([], 0)


@pytest.mark.parametrize("fn", ["forecast_headcount", "attrition_risk"])
def test_the_workforce_stub_refuses_instead_of_answering(fn):
    with pytest.raises(NotImplementedError):
        getattr(stub_workforce, fn)([], 6)


def test_no_stub_returns_a_number_anyone_could_act_on():
    """The general property. A stub that RETURNS anything can be rendered; a
    stub that raises cannot reach a customer."""
    for module in (stub_comp, stub_workforce):
        for name in dir(module):
            if name.startswith("_"):
                continue
            fn = getattr(module, name)
            if not callable(fn) or isinstance(fn, type):
                continue
            with pytest.raises(NotImplementedError):
                fn([], 1)


# ---------------------------------------------------------------------------
# The newly wired detector has to actually detect. Swapping a stub that always
# said "nothing found" for an implementation that also always says "nothing
# found" would be no improvement at all -- and would be harder to notice.
# ---------------------------------------------------------------------------

# The detector fires when someone is BOTH above 90% of the top salary AND below
# the group average -- the shape where a band has bunched up at the ceiling and
# a long-tenured employee has been overtaken. Note that both conditions must
# hold: in a three-person group, anyone at 96% of the top is usually also above
# the mean, so it takes a cluster near the ceiling to produce real compression.
COMPRESSED = [
    {"id": "a", "title": "Software Engineer", "level": 2, "salary": 150_000},
    {"id": "b", "title": "Software Engineer", "level": 2, "salary": 155_000},
    {"id": "c", "title": "Software Engineer", "level": 2, "salary": 155_000},
    {"id": "d", "title": "Software Engineer", "level": 2, "salary": 155_000},
]

HEALTHY = [
    {"id": "a", "title": "Software Engineer", "level": 2, "salary": 100_000},
    {"id": "b", "title": "Software Engineer", "level": 2, "salary": 150_000},
    {"id": "c", "title": "Software Engineer", "level": 2, "salary": 200_000},
]


def test_the_detector_fires_on_planted_compression():
    """MUTATION CONTROL, positive."""
    result = real.detect_pay_compression(COMPRESSED)
    assert result["issues"], (
        "the wired detector found no compression in a group bunched at the top "
        "with one employee below both the ceiling and the group average. "
        "It is not looking."
    )
    assert result["issues"][0]["employee_id"] == "a"


def test_the_detector_is_silent_on_a_healthy_band():
    """MUTATION CONTROL, negative. A detector that flags everything is as
    useless as one that flags nothing, and gets switched off faster."""
    result = real.detect_pay_compression(HEALTHY)
    assert result["issues"] == [], f"flagged a well-spread band: {result['issues']}"


def test_the_detector_reports_what_it_examined():
    result = real.detect_pay_compression(COMPRESSED)
    assert result["groups_analyzed"] == 1, (
        "the caller cannot tell an empty result from an unexamined one without "
        "knowing how many groups were actually analysed"
    )


def test_an_empty_roster_is_not_a_clean_bill_of_health():
    """Zero issues from zero employees must be distinguishable from zero issues
    after a real examination."""
    result = real.detect_pay_compression([])
    assert result["issues"] == []
    assert result["groups_analyzed"] == 0, (
        "an empty roster reported the same 'groups_analyzed' as a real run, so "
        "'no issues' cannot be distinguished from 'nothing was examined'"
    )
