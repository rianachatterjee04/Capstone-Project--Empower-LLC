"""Tests for the LLM-first path in generate_candidate_specific_questions.

Covers:
  * happy path uses mocked llm_complete output (not local templates)
  * skill-gap + ownership probes still append after LLM questions
  * malformed / empty LLM payloads fall back to _LOCAL_QUESTION_TEMPLATES
  * partial malformed entries are skipped without raising
  * llm_complete is None → pure local-template path

Run:  python -m pytest tests/test_generate_candidate_specific_questions_llm.py -v
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from app.services import interview_copilot_service as S


_LLM_JSON = json.dumps({
    "questions": [
        {
            "competency": "technical_depth",
            "text": "Describe the specific caching strategy you'd use for a high-traffic API, and why.",
            "rationale": "Tests real depth beyond buzzwords.",
        },
        {
            "competency": "problem_solving",
            "text": "Walk me through how you would debug a cascading failure in a microservices mesh.",
            "rationale": "Probes real incident judgement.",
        },
    ]
})

_JOB = "Senior Software Engineer"
_TYPE = "technical"
_SUMMARY = "Staff engineer with distributed systems experience."


def _call(*, summary=_SUMMARY, skill_gaps=None, n_questions=7, interview_id=None):
    return S.generate_candidate_specific_questions(
        interview_id=interview_id or str(uuid.uuid4()),
        interview_type=_TYPE,
        job_title=_JOB,
        candidate_summary=summary,
        skill_gaps=skill_gaps,
        n_questions=n_questions,
    )


def _local_baseline(*, summary=_SUMMARY, skill_gaps=None, n_questions=7):
    """Same call with llm_complete forced off — the pre-feature local path."""
    with patch.object(S, "llm_complete", None):
        return _call(summary=summary, skill_gaps=skill_gaps, n_questions=n_questions)


def _texts(qs):
    return [q.text for q in qs]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_llm_path_produces_role_specific_questions():
    with patch.object(S, "llm_complete", return_value=_LLM_JSON) as mock_llm:
        qs = _call(skill_gaps=[], summary="No ownership keyword here.")

    assert mock_llm.called
    texts = _texts(qs)
    assert "Describe the specific caching strategy you'd use for a high-traffic API, and why." in texts
    assert "Walk me through how you would debug a cascading failure in a microservices mesh." in texts

    by_text = {q.text: q for q in qs}
    q1 = by_text["Describe the specific caching strategy you'd use for a high-traffic API, and why."]
    q2 = by_text["Walk me through how you would debug a cascading failure in a microservices mesh."]
    assert q1.competency == "technical_depth"
    assert q2.competency == "problem_solving"
    assert q1.generated_by_ai is True
    assert q2.generated_by_ai is True

    # Prove we did not silently use the local templates for these competencies.
    local_texts = set(_texts(_local_baseline(skill_gaps=[], summary="No ownership keyword here.")))
    assert q1.text not in local_texts
    assert q2.text not in local_texts


def test_llm_path_still_appends_skill_gap_and_ownership_probes():
    summary = "She owned the billing platform end-to-end for three years."
    with patch.object(S, "llm_complete", return_value=_LLM_JSON):
        qs = _call(summary=summary, skill_gaps=["Kubernetes", "GraphQL"], n_questions=10)

    texts = _texts(qs)
    assert "Describe the specific caching strategy you'd use for a high-traffic API, and why." in texts
    assert any("Kubernetes" in t and "resume doesn't call out" in t for t in texts)
    assert any("GraphQL" in t and "resume doesn't call out" in t for t in texts)
    assert (
        "You mention ownership of multiple workstreams — pick the one that taught you "
        "the most, walk me through what you'd do differently."
    ) in texts


# ---------------------------------------------------------------------------
# Fallback paths
# ---------------------------------------------------------------------------
def test_llm_returns_malformed_json_falls_back_to_local_templates():
    with patch.object(S, "llm_complete", return_value="this is not json at all"):
        qs = _call(skill_gaps=[], summary="plain summary")

    expected = _local_baseline(skill_gaps=[], summary="plain summary")
    assert _texts(qs) == _texts(expected)
    assert [q.competency for q in qs] == [q.competency for q in expected]


def test_llm_returns_empty_questions_list_falls_back_to_local_templates():
    with patch.object(S, "llm_complete", return_value='{"questions": []}'):
        qs = _call(skill_gaps=[], summary="plain summary")

    expected = _local_baseline(skill_gaps=[], summary="plain summary")
    assert len(qs) > 0, "empty LLM list must not yield zero questions"
    assert _texts(qs) == _texts(expected)


def test_llm_returns_questions_missing_required_fields_falls_back_or_skips_gracefully():
    payload = json.dumps({
        "questions": [
            {"competency": "technical_depth", "rationale": "missing text"},
            {"text": "A question with no competency.", "rationale": "missing competency"},
            {
                "competency": "problem_solving",
                "text": "Only this one is complete and usable.",
                "rationale": "ok",
            },
        ]
    })
    with patch.object(S, "llm_complete", return_value=payload):
        qs = _call(skill_gaps=[], summary="plain summary", n_questions=10)

    assert all((q.text or "").strip() for q in qs), "no empty-text InterviewQuestion allowed"
    assert all((q.competency or "").strip() for q in qs)
    # Current impl skips bad rows and keeps the one valid LLM question (no raise).
    assert any(q.text == "Only this one is complete and usable." for q in qs)
    assert not any(q.text == "A question with no competency." for q in qs)


def test_llm_unavailable_falls_back_to_local_templates():
    with patch.object(S, "llm_complete", None):
        qs = _call(skill_gaps=[], summary="plain summary")

    expected = _local_baseline(skill_gaps=[], summary="plain summary")
    assert _texts(qs) == _texts(expected)
    assert [q.competency for q in qs] == [q.competency for q in expected]
    assert len(qs) > 0
