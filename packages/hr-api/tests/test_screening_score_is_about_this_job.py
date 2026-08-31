"""
A candidate is scored against the job they applied to, using words they wrote.

WHY THIS IS A TEST
explainable_ai_score matched a resume against a fixed sixteen-word list --
python, fastapi, react, aws, hr, payroll and so on -- and never looked at the
job at all. It was not a fit score; it was a software-vocabulary score. Its
number set the candidate's ai_summary AND drove their pipeline status:

    status = "screened" if score >= 40 else "new"

So the damage was not cosmetic:

  * A CDL driver applying to a driving job scored 0, summary "Matched skills:
    none", and could never reach "screened".
  * A Senior Accountant scored 10 with the summary "Matched skills: ui",
    because "ui" is a substring of "NetSuite".
  * "Worked through rapid growth; therapy dogs in the office" scored 20 and was
    credited with "api" -- inside "rapid" -- and "hr" -- inside "through".

Substring matching against a fixed list manufactures confident claims about a
person from words they never wrote, and then files them under that person's
name. It is the same class as the hard-coded "5 years building async Python
backends": a polished screen describing somebody who does not exist.
"""
from __future__ import annotations

import pytest

from app.api.routers.recruiting import explainable_ai_score as score

DRIVING_JOB = ("CDL Driver Regional Reefer. Class A CDL required, clean MVR, "
               "reefer experience, OTR and regional routes, DOT inspections, "
               "dispatch communication.")
ACCOUNTING_JOB = ("Senior Accountant. Owns monthly close, balance sheet "
                  "reconciliations, accrual schedules, GAAP, external audit "
                  "support, NetSuite.")

DRIVER_RESUME = ("Kenworth T680 reefer, 6 years OTR and regional. Class A CDL, "
                 "clean MVR. Tanker endorsement. Dispatch communication, DOT "
                 "inspections.")
ACCOUNTANT_RESUME = ("Eight years corporate accounting. Monthly close, balance "
                     "sheet reconciliations, accrual schedules, GAAP, external "
                     "audit support, NetSuite.")
ENGINEER_RESUME = "Five years building async Python backends in FastAPI and Postgres."
IRRELEVANT = "Worked through rapid growth; therapy dogs in the office."


def test_a_qualified_driver_scores_on_a_driving_job():
    s, rationale, matched = score(DRIVER_RESUME, DRIVING_JOB)
    assert s is not None and s > 0, (
        f"a Class A CDL driver with reefer and OTR experience scored {s} on a "
        f"reefer driving job: {rationale}"
    )
    assert "cdl" in matched


def test_a_qualified_accountant_scores_on_an_accounting_job():
    s, _, matched = score(ACCOUNTANT_RESUME, ACCOUNTING_JOB)
    assert s is not None and s > 0
    assert {"close", "accrual"} <= set(matched)


@pytest.mark.parametrize("resume,job,who", [
    (ENGINEER_RESUME, DRIVING_JOB, "a backend engineer on a driving job"),
    (DRIVER_RESUME, ACCOUNTING_JOB, "a driver on an accounting job"),
    (ACCOUNTANT_RESUME, DRIVING_JOB, "an accountant on a driving job"),
])
def test_an_unrelated_background_does_not_score(resume, job, who):
    s, _, matched = score(resume, job)
    assert s == 0 and matched == [], f"{who} scored {s} on {matched}"


def test_ordinary_prose_is_not_credited_with_skills():
    """The therapy-dog case. This is the one that shipped a false claim."""
    s, rationale, matched = score(IRRELEVANT, ACCOUNTING_JOB)
    assert matched == [], f"credited with {matched} from: {IRRELEVANT!r}"
    assert s == 0
    for invented in ("api", "hr", "ui", "sql"):
        assert invented not in rationale, (
            f"the rationale claims {invented!r}, which the candidate never wrote"
        )


def test_substrings_are_never_matched():
    """MUTATION CONTROL for the matching itself. Each of these contains a
    former keyword INSIDE a longer word. Whole-word matching must ignore them."""
    job = "We need api and hr and ui and sql skills."
    for prose, hidden in [("rapid growth", "api"),
                          ("worked through it", "hr"),
                          ("we use NetSuite", "ui"),
                          ("PostgreSQL tuning", "sql")]:
        _, _, matched = score(prose, job)
        assert hidden not in matched, (
            f"{hidden!r} was matched inside {prose!r} -- substring matching is back"
        )


def test_a_job_with_no_description_is_not_scored():
    """An unscreened candidate is a state, not a zero. Scoring them against
    nothing and calling it 0 is what kept the driver out of the pipeline."""
    s, rationale, matched = score(ACCOUNTANT_RESUME, None)
    assert s is None, f"scored {s} against a job with no description"
    assert "not scored" in rationale.lower()
    assert matched == []


def test_a_candidate_with_no_resume_is_not_scored():
    s, rationale, _ = score("", ACCOUNTING_JOB)
    assert s is None
    assert "no resume" in rationale.lower()


def test_the_score_is_a_proportion_of_what_the_job_asked_for():
    """It has to mean something. A resume echoing the whole posting scores 100;
    the same resume against a longer posting scores less."""
    s_exact, _, _ = score(ACCOUNTING_JOB, ACCOUNTING_JOB)
    assert s_exact == 100
    longer = ACCOUNTING_JOB + " Also requires SAP, Hyperion, Blackline and Workiva."
    s_partial, _, _ = score(ACCOUNTING_JOB, longer)
    assert s_partial < 100


def test_an_unscored_candidate_is_not_advanced_to_screened():
    """The pipeline consequence, asserted at the call site's rule."""
    import ast, pathlib
    src = pathlib.Path("app/api/routers/recruiting.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "create_candidate")
    body = ast.unparse(fn)
    assert "score is not None and score >= 40" in body, (
        "a candidate whose score could not be computed can still be marked "
        "'screened' -- an unread resume then looks reviewed"
    )
