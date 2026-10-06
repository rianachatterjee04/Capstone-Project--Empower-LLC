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

TWO PATHS
generate_interview_plan tries the LLM first and falls back to local templates
when llm_complete is None or the call fails. Exact fallback wording is checked
only with llm_complete mocked to None, so a configured API key cannot change
those assertions. The LLM path is checked separately against a fixed fake
response: no false resume claim when there is no summary, real resume content
when there is one, and candidate_specific_notes always present.
"""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch

from app.services import interview_copilot_service as S


RESUME_CLAIMS = ("resume signals", "resume reads", "resume gaps",
                 "the resume understates", "candidate summary.")

_SUMMARY = "Owned the monthly close for three entities."
_SKILLS = ["close", "ASC 606"]
_GAPS = ["SOX"]


def _plan(summary="", skills=None, gaps=None):
    """Local-template path only. A live API key must not change these results."""
    with patch.object(S, "llm_complete", None):
        return S.generate_interview_plan(
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


def _assert_no_resume_claim(plan):
    text = _all_text(plan)
    found = [c for c in RESUME_CLAIMS if c in text]
    assert found == [], (
        "the plan asserts things about a resume it was never given: "
        f"{found}\n{text}")


def _assert_notes_present(plan):
    note = plan.get("candidate_specific_notes")
    assert isinstance(note, str) and note.strip(), (
        "candidate_specific_notes is missing or empty")


# ---------------------------------------------------------------------------
# Local fallback — exact template wording (llm_complete is None)
# ---------------------------------------------------------------------------
def test_no_summary_means_no_resume_claim():
    _assert_no_resume_claim(_plan())


def test_no_summary_says_what_the_plan_was_built_on():
    plan = _plan()
    note = plan["candidate_specific_notes"].lower()
    assert "no candidate summary" in note, note
    assert "senior accountant" in note, "the note does not name the role it fell back to"


def test_a_real_summary_still_gets_resume_specific_language():
    # CONTROL. The fix must not flatten the useful case into the cautious one.
    plan = _plan(summary=_SUMMARY, skills=_SKILLS, gaps=_GAPS)
    text = _all_text(plan)
    assert "resume signals strong" in text
    assert "limited evidence of sox" in text
    assert "no candidate summary" not in text


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_whitespace_only_summary_counts_as_absent(blank):
    assert "no candidate summary" in _plan(summary=blank)["candidate_specific_notes"].lower()


# ---------------------------------------------------------------------------
# LLM path — properties, not exact fallback wording
# ---------------------------------------------------------------------------
def _llm_plan_json(*, notes, concerns, positives, verify, agenda_topic):
    return json.dumps({
        "focus_areas": ["close_process", "reconciliations"],
        "agenda": [{"minutes": 10, "topic": agenda_topic}],
        "verify": verify,
        "concerns_to_explore": concerns,
        "positive_signals_to_confirm": positives,
        "candidate_specific_notes": notes,
    })


_LLM_NO_SUMMARY = _llm_plan_json(
    notes=(
        "Candidate skills are currently unknown; the interview will focus on "
        "uncovering technical expertise for the Senior Accountant role."
    ),
    concerns=["Establish specific outcomes from scratch; nothing is on file yet."],
    positives=["Confirm whether the candidate has owned a close end to end."],
    verify=[],
    agenda_topic="Open-ended deep dive — background and scope",
)

_LLM_WITH_SUMMARY = _llm_plan_json(
    notes=(
        "Candidate has solid experience owning the monthly close for three "
        "entities, with close and ASC 606 called out; the SOX gap still needs a probe."
    ),
    concerns=["Ask how they would get up to speed on SOX."],
    positives=["Ownership of the monthly close across three entities."],
    verify=["Direct experience with close", "Direct experience with ASC 606"],
    agenda_topic="Deep dive on the monthly close the candidate described",
)


def _plan_from_llm(raw, summary="", skills=None, gaps=None):
    with patch.object(S, "llm_complete", return_value=raw) as mock_llm:
        plan = S.generate_interview_plan(
            interview_type="onsite",
            job_title="Senior Accountant",
            job_description="",
            candidate_summary=summary,
            extracted_skills=skills or [],
            skill_gaps=gaps or [],
        )
    assert mock_llm.called, "the LLM path did not run"
    assert plan.get("generated_by") == "llm"
    return plan


def test_llm_no_summary_means_no_resume_claim():
    plan = _plan_from_llm(_LLM_NO_SUMMARY)
    _assert_notes_present(plan)
    _assert_no_resume_claim(plan)
    assert "senior accountant" in plan["candidate_specific_notes"].lower()


def test_llm_real_summary_references_resume_content():
    plan = _plan_from_llm(
        _LLM_WITH_SUMMARY, summary=_SUMMARY, skills=_SKILLS, gaps=_GAPS,
    )
    _assert_notes_present(plan)
    text = _all_text(plan)
    assert "monthly close" in text
    assert "asc 606" in text
    assert "sox" in text
    assert "no candidate summary" not in text
    # Useful case must not collapse into a false "we never saw a resume" note,
    # and must not invent the local template's exact resume-claim phrases.
    _assert_no_resume_claim(plan)


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_llm_blank_summary_does_not_claim_a_resume(blank):
    plan = _plan_from_llm(_LLM_NO_SUMMARY, summary=blank)
    _assert_notes_present(plan)
    _assert_no_resume_claim(plan)
