"""
The questions asked come from the job, not from a software template.

WHY THIS IS A TEST
_COMPETENCY_BANK was keyed by INTERVIEW TYPE alone, and the job title was never
consulted. So every onsite interview probed technical_depth, collaboration,
ownership and communication, and the first question asked was:

    "Describe a system you owned end-to-end. Where did you make a non-obvious
     trade-off?"

A CDL driver interviewing for a regional reefer run was asked that. Browser-
verified before the fix: the plan's agenda read "Competency probes:
technical_depth, collaboration, ownership, communication" for a driver, and
nothing about reefer units, hours, detention or dispatch could ever appear
because those competencies did not exist.

An accountant would have got the same. So would a dispatcher and a freight
broker.

This is the same family as the hard-coded "5 years building async Python
backends": the product presenting software as the default shape of work.
Personalisation that is really a template is worse than an openly generic
interview, because the candidate can tell we did not read the role and the
recruiter collects evidence about competencies the job does not need.

The role now selects the competencies and the interview type shapes the depth.
A role we cannot classify gets the universal set -- never the software set,
because "unknown" must not quietly mean "engineer".
"""
from __future__ import annotations

import pytest

from app.services.interview_copilot_service import (
    _LOCAL_QUESTION_TEMPLATES,
    competencies_for,
    role_family,
)

# Vocabulary that would be absurd in another line of work.
SOFTWARE_ONLY = ("system you owned end-to-end", "architecture", "code is 'done enough'",
                 "non-obvious trade-off")
DRIVING_ONLY = ("hauling", "otr", "dispatch", "roadside", "receiver")
ACCOUNTING_ONLY = ("month-end close", "reconciliation", "accrue", "revenue recognition")


def _questions(job_title: str, interview_type: str = "onsite") -> str:
    comps = competencies_for(interview_type, job_title)
    out = []
    for c in comps:
        out += _LOCAL_QUESTION_TEMPLATES.get(c, [])
    return " ".join(out).lower()


@pytest.mark.parametrize("title,family", [
    ("CDL Driver — Regional Reefer", "driving"),
    ("OTR Truck Driver", "driving"),
    ("Senior Accountant", "accounting"),
    ("Assistant Controller", "accounting"),
    ("Dispatcher", "dispatch"),
    ("Freight Broker", "brokerage"),
    ("Senior Platform Engineer", "software"),
    ("Backend Developer", "software"),
])
def test_the_role_is_recognised(title, family):
    assert role_family(title) == family


@pytest.mark.parametrize("title", [
    "Underwater Basket Weaver", "Head Chef", "Veterinary Nurse", "", None,
])
def test_an_unclassified_role_gets_universal_competencies_not_software(title):
    """The important negative. 'We could not tell' must not become 'engineer'."""
    comps = competencies_for("onsite", title)
    for software in ("technical_depth", "system_design", "code_quality"):
        assert software not in comps, (
            f"{title!r} was given {software} — an unrecognised role is being "
            f"treated as a software role by default"
        )
    assert "communication" in comps


def test_a_driver_is_asked_about_driving():
    text = _questions("CDL Driver — Regional Reefer")
    for expected in DRIVING_ONLY:
        assert expected in text, f"a CDL driver is never asked about {expected!r}"


def test_a_driver_is_never_asked_a_software_question():
    """The defect, named. This was live and browser-verified."""
    text = _questions("CDL Driver — Regional Reefer")
    for software in SOFTWARE_ONLY:
        assert software not in text, (
            f"a CDL driver is asked to {software!r}"
        )


def test_an_accountant_is_asked_about_accounting():
    text = _questions("Senior Accountant")
    for expected in ACCOUNTING_ONLY:
        assert expected in text, f"a Senior Accountant is never asked about {expected!r}"


def test_an_accountant_is_never_asked_a_software_question():
    text = _questions("Senior Accountant")
    for software in SOFTWARE_ONLY:
        assert software not in text, f"a Senior Accountant is asked to {software!r}"


def test_an_engineer_still_gets_engineering_questions():
    """CONTROL. Making other roles work must not break the one that already did."""
    text = _questions("Senior Platform Engineer")
    assert "system you owned end-to-end" in text
    assert "architecture" in text


@pytest.mark.parametrize("title", [
    "CDL Driver — Regional Reefer", "Senior Accountant", "Dispatcher",
    "Freight Broker", "Senior Platform Engineer",
])
def test_every_selected_competency_has_a_question(title):
    """A competency with no template is a silently shorter interview."""
    missing = [c for c in competencies_for("onsite", title)
               if not _LOCAL_QUESTION_TEMPLATES.get(c)]
    assert missing == [], f"{title} selects {missing}, which have no questions"


@pytest.mark.parametrize("itype", ["screen", "onsite", "final", "culture"])
def test_every_interview_type_still_produces_questions(itype):
    for title in ("CDL Driver — Regional Reefer", "Senior Accountant", None):
        comps = competencies_for(itype, title)
        assert comps, f"{itype} for {title!r} selected no competencies"
        assert any(_LOCAL_QUESTION_TEMPLATES.get(c) for c in comps), (
            f"{itype} for {title!r} produced no questions at all")


def test_the_roles_do_not_share_their_specific_questions():
    """MUTATION CONTROL. If every role resolved to the same competencies, every
    assertion above would still pass for the wrong reason."""
    driver = set(competencies_for("onsite", "CDL Driver — Regional Reefer"))
    accountant = set(competencies_for("onsite", "Senior Accountant"))
    engineer = set(competencies_for("onsite", "Senior Platform Engineer"))
    assert driver != accountant != engineer
    assert not (driver & engineer), f"driver and engineer share {driver & engineer}"
    assert not (accountant & engineer), f"accountant and engineer share {accountant & engineer}"
