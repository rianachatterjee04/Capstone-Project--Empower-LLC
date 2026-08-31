"""
Findability guardrails.

The reported bug was: built capabilities (AI Interviewer, Performance, Equity,
Recruiting) existed in the backend but the owner "could not find them" in the UI
because they were buried / mislabelled in the nav.

These tests read the two frontend nav-config.ts files and assert that every
major capability is exposed by a nav entry AND that the backend router that
powers it is actually mounted. They are deliberately string-level (no TS build
needed) so they fail loudly if a future edit drops a capability from the nav.
"""
# CAP TABLE IS NOT PART OF THIS BUILD.
#
# The equity / cap-table module (grants, stakeholders, 409A valuations,
# ASC 718) is deliberately excluded from this deployment, so the nav links,
# labels and routes that used to be asserted here would now be asserting the
# presence of something that was removed on purpose. They are removed rather
# than skipped: a skipped assertion still reads as coverage of a capability
# that is not here.

from __future__ import annotations

import os

import pytest

HERE = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EMPLOYER_NAV = os.path.join(
    REPO, "packages", "hr-web-employer", "src", "components", "nav-config.ts")
EMPLOYEE_NAV = os.path.join(
    REPO, "packages", "hr-web-employee", "src", "components", "nav-config.ts")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Employer nav: every flagship capability must be one click away.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def employer_nav() -> str:
    assert os.path.exists(EMPLOYER_NAV), f"missing {EMPLOYER_NAV}"
    return _read(EMPLOYER_NAV)


@pytest.mark.parametrize("route", [
    "/app/interview-ai",      # AI Interviewer (the reported-missing one)
    "/app/performance",       # Performance reviews (the reported-missing one)
    "/app/talent",            # recruiting pipeline
    "/app/recruiter-cockpit", # resume AI screening
    "/app/interviews",        # scorecards
    "/app/calibration",       # calibration
    "/app/goals",             # goals / OKRs
    "/app/comp",              # compensation cycle
    "/app/bonuses",           # bonuses
    "/app/marketplace",       # talent marketplace / succession
    "/app/risk",              # attrition / flight risk
    "/app/analytics",         # people analytics
    "/app/learning",          # learning
    "/app/ombudsman",         # ombudsman
])
def test_employer_nav_exposes_route(employer_nav, route):
    assert route in employer_nav, f"employer nav is missing a link to {route}"


@pytest.mark.parametrize("label", [
    "AI Interviewer",
    "Performance reviews",
    "Resume AI screening",
])
def test_employer_nav_has_clear_labels(employer_nav, label):
    assert label in employer_nav, f"employer nav is missing the clear label '{label}'"


def test_employer_nav_flags_ai_features(employer_nav):
    # AI-powered surfaces are badged so they are discoverable at a glance.
    assert employer_nav.count("aiHinted: true") >= 20


def test_employer_nav_has_capability_groups(employer_nav):
    for group in ('label: "Recruiting"', 'label: "Performance"',
                  'label: "Compensation"',
                  'label: "People Analytics"'):
        assert group in employer_nav, f"employer nav missing group {group}"


# ---------------------------------------------------------------------------
# Employee nav: clear self-service.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def employee_nav() -> str:
    assert os.path.exists(EMPLOYEE_NAV), f"missing {EMPLOYEE_NAV}"
    return _read(EMPLOYEE_NAV)


@pytest.mark.parametrize("route", [
    "/app/twin",          # my profile
    "/app/payroll",       # my pay
    "/app/compensation",  # my total comp
    "/app/performance",   # my reviews / goals
    "/app/pto",           # PTO
    "/app/onboarding",    # tasks / onboarding
])
def test_employee_nav_exposes_self_service(employee_nav, route):
    assert route in employee_nav, f"employee nav is missing self-service link {route}"


def test_employee_nav_surfaces_total_comp(employee_nav):
    """Cap table is not in this build, so "My equity" is gone with it. Total
    compensation stays: it is cash-only here and says so."""
    assert "Total comp" in employee_nav or "compensation" in employee_nav.lower()
    assert "My equity" not in employee_nav, (
        "the employee nav still offers an equity page that this build does not "
        "serve"
    )


# ---------------------------------------------------------------------------
# Backend must actually mount the routers those nav links depend on.
# ---------------------------------------------------------------------------

def test_backend_mounts_findable_routers():
    from app.api.router import api_router
    paths = {r.path for r in api_router.routes}
    # A representative endpoint from each flagship capability.
    required = [
        "/ai-interview/sessions",           # AI Interviewer
        "/performance/reviews",             # Performance
        "/resume-ai/rank",                  # Resume AI screening
        "/calibration/grid",               # Calibration
        "/marketplace/roles",              # Talent marketplace / succession
    ]
    for p in required:
        assert p in paths, f"backend does not mount {p} (nav would 404)"
