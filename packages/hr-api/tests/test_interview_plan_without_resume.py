"""
An interview plan built with no candidate summary does not claim to have read
a resume.

WHY THIS IS A TEST
The interview prep page hard-coded its candidate context: "5 years building
async Python backends", the skills python/fastapi/postgres/asyncio, the gaps
llm/embeddings, and an AI MATCH of 78 — as literals, for every interview. A
Senior Accountant was shown a backend engineer's profile and a confident score
that was a constant.

Those same invented strings were also POSTed to generate-plan and
generate-questions, so the AI output a buyer judges us on was derived from a
profile belonging to nobody. Removing them exposed what the generator does with
honest input: it still printed "Resume signals strong on the listed skills" and
"resume reads strong but generic" for a candidate whose summary was empty.

A plan built on the role alone is a perfectly good plan. Claiming to have read
a resume that does not exist is the part that cannot ship.
"""
from __future__ import annotations

import pytest

from app.services.interview_copilot_service import generate_interview_plan

RESUME_CLAIMS = ("resume signals", "resume reads", "resume gaps",
                 "the resume understates", "candidate summary.")


def _plan(summary="", skills=None, gaps=None):
    return generate_interview_plan(
        interview_type="onsite",
        job_title="Senior Accountant",
        job_description="",
        candidate_summary=summary,
        extracted_skills=skills or [],
        skill_gaps=gaps or [],
    )


def _all_text(plan) -> str:
    parts = [plan["candidate_specific_notes"]]
    parts += plan["concerns_to_explore"]
    parts += plan["positive_signals_to_confirm"]
    parts += [a["topic"] for a in plan["agenda"]]
    parts += plan["verify"]
    return " ".join(parts).lower()


def test_no_summary_means_no_resume_claim():
    text = _all_text(_plan())
    found = [c for c in RESUME_CLAIMS if c in text]
    assert found == [], (
        "the plan asserts things about a resume it was never given: "
        f"{found}\n{text}")


def test_no_summary_says_what_the_plan_was_built_on():
    plan = _plan()
    note = plan["candidate_specific_notes"].lower()
    assert "no candidate summary" in note, note
    assert "senior accountant" in note, "the note does not name the role it fell back to"


def test_a_real_summary_still_gets_resume_specific_language():
    # CONTROL. The fix must not flatten the useful case into the cautious one.
    plan = _plan(summary="Owned the monthly close for three entities.",
                 skills=["close", "ASC 606"], gaps=["SOX"])
    text = _all_text(plan)
    assert "resume signals strong" in text
    assert "limited evidence of sox" in text
    assert "no candidate summary" not in text


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_whitespace_only_summary_counts_as_absent(blank):
    assert "no candidate summary" in _plan(summary=blank)["candidate_specific_notes"].lower()
