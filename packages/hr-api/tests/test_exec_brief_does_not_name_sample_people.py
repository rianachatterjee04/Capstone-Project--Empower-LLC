"""
The executive brief does not name an invented person as a retention concern.

WHY THIS IS A TEST
/app/brief opened with:

    "1 high flight-risk employee need attention this week."
    "... Top retention concern: Avery Chen."

Avery Chen is one of three invented people in cpo_service's sample cohort,
under a comment reading "Synthetic attrition (until production model is
wired)". The organisation reading that brief has one employee, a CDL driver.

This is the first line an owner reads in the morning. Naming somebody as the
company's top retention concern is the most consequential claim about an
individual the product makes, and it is also the one most likely to be repeated
out loud in a meeting.

The sample cohort still runs, because the attrition model is worth showing. It
no longer leads the brief, no longer supplies a name, and says what it is.
"""
from __future__ import annotations

import inspect
import re

from app.services import cpo_service as C

SAMPLE_NAMES = ("Avery Chen", "Jordan Patel", "Riley Singh")


def _code() -> str:
    """Source with docstrings and comments removed.

    The first version of this checked raw source and failed on the comment that
    EXPLAINS the fix, which quotes the old line. That is the fourth guard
    tonight to fire on the prose describing the thing it guards. Code only.
    """
    src = re.sub(r'"""[\s\S]*?"""', "", inspect.getsource(C))
    return re.sub(r"(?m)^\s*#.*$", "", src)


def test_no_sample_name_is_presented_as_a_retention_concern():
    body = _code()
    assert "Top retention concern: {high_risk[0].name}" not in body, (
        "the brief names the top entry of a sample cohort as this company's "
        "retention concern")
    # the phrase itself must not be reachable with a sample name
    assert "Top retention concern" not in body, (
        "the brief still asserts a top retention concern; it has no signal for "
        "real employees to base one on")


def test_the_flight_risk_headline_cannot_lead_the_brief():
    body = _code()
    assert "high flight-risk employee" not in body.split("HealthMetric")[0], (
        "a headline branch still leads on flight risk computed from sample "
        "people")


def test_the_sample_cohort_is_still_reported_as_a_sample():
    """CONTROL. Removing the claim must not remove the disclosure with it."""
    src = inspect.getsource(C)
    assert "sample people" in src or "sample cohort" in src, (
        "the brief no longer says the attrition numbers come from a sample")
    assert "illustrative" in src


def test_the_sample_names_are_still_only_in_the_cohort():
    """They may exist as fixtures; they may not be quoted as findings."""
    for name in SAMPLE_NAMES:
        occurrences = [ln for ln in _code().splitlines()
                       if name in ln and "AttritionFeatures(" not in ln]
        assert occurrences == [], (
            f"{name} appears outside the sample cohort definition: {occurrences}")
