"""
A recommendation to go and talk to someone says whether that someone exists.

WHY THIS IS A TEST
The CPO report told an executive:

    "Retention conversation recommended for Avery Chen"
    "Compa-ratio below 0.85 (under-paid vs. band midpoint).; No raise in 22
     months.; Strong performer with no promotion in 24+ months."

Avery Chen is one of three illustrative people the attrition model scores. The
organisation reading it has one employee, and he is not her.

The half-fix is what makes this worth pinning. The PRIORITY block on the same
report already said, correctly, "Attrition model is running on sample data, not
your employees ... It scored 3 illustrative people". The RECOMMENDATION built
from the very same list said nothing — and the recommendation is the actionable
one. A priority is read; a recommendation sends a manager to have a
conversation, with compensation details attached to a name.

Disclosure has to travel with the claim, not sit in a neighbouring block.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import cpo_service as C

SAMPLE_NAMES = ("Avery Chen", "Jordan Patel", "Riley Singh", "Sam Rivera",
                "Morgan Lee", "Emily Stone")


class _EmptyResult:
    """Every count comes back 0 — an organisation with no data of its own.

    That is the case that matters: with nothing real to report on, whatever the
    report still says about named people came from somewhere other than this
    organisation's records.
    """

    def first(self):
        return (0,)

    def scalar(self):
        return 0

    def mappings(self):
        return self

    def all(self):
        return []


class _EmptyDB:
    async def execute(self, *_a, **_k):
        return _EmptyResult()


def _report(org="11111111-1111-1111-1111-111111111111"):
    result = asyncio.run(C.build_report(_EmptyDB(), org))
    return result if isinstance(result, dict) else result.to_dict()


def test_every_recommendation_naming_a_sample_person_is_marked():
    rec = _report()["recommendations"]
    assert rec, "no recommendations produced; this test would pass vacuously"
    unmarked = [
        r["headline"] for r in rec
        if any(n in r["headline"] for n in SAMPLE_NAMES) and not r.get("is_sample")
    ]
    assert unmarked == [], (
        "these recommend action about an invented person without saying so:\n  "
        + "\n  ".join(unmarked)
    )


def test_the_marked_recommendation_explains_itself_in_its_own_words():
    """A boolean nothing renders is not a disclosure. The rationale a manager
    actually reads has to carry it."""
    rec = _report()["recommendations"]
    sampled = [r for r in rec if r.get("is_sample")]
    if not sampled:
        pytest.skip("no sample-derived recommendations in this org's report")
    for r in sampled:
        assert "not an employee in your organisation" in r["rationale"], (
            f"{r['headline']!r} is flagged is_sample but its rationale does not "
            f"say so: {r['rationale']!r}"
        )
        assert "(sample)" in r["headline"], (
            "the headline alone reads as a real recommendation"
        )


def test_the_check_can_see_an_unmarked_sample_name():
    """MUTATION CONTROL. If the scan could not spot a sample name in a headline,
    the assertion above would pass over anything."""
    fake = [{"headline": "Retention conversation recommended for Avery Chen",
             "rationale": "x", "is_sample": False}]
    unmarked = [r["headline"] for r in fake
                if any(n in r["headline"] for n in SAMPLE_NAMES) and not r.get("is_sample")]
    assert unmarked, "the detector cannot see an unmarked sample person"


def test_a_recommendation_about_nobody_in_particular_is_not_flagged():
    """CONTROL, the other direction. Recommendations that name no person must
    not be swept up — over-marking teaches readers to ignore the marker."""
    rec = _report()["recommendations"]
    impersonal = [r for r in rec if not any(n in r["headline"] for n in SAMPLE_NAMES)]
    for r in impersonal:
        assert not r.get("is_sample"), (
            f"{r['headline']!r} names no sample person but is flagged as sample"
        )
