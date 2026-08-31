"""The deny-by-default half of the candidate boundary.

The module docstring for app.interview.dto has always said this:

    "DENY BY DEFAULT. candidate_safe() builds its output from an ALLOWLIST. ...
     The opposite design -- strip the fields we currently consider sensitive --
     fails the moment anyone adds a field, which is the moment nobody is
     looking."

and `candidate_safe` implemented the opposite design: it refused ~40 known
names and returned everything else. The allowlist tuples were defined and the
helper to apply them existed, unused. A security control that does not do what
its own documentation says is worse than a missing one, because the name
`candidate_safe` is trusted by whoever writes the next endpoint.

The tests here are specifically about the fields NOBODY HAS THOUGHT OF, since
those are the only ones a denylist misses.
"""
from __future__ import annotations

import pytest

from app.interview import dto as DTO


# ── the gap the denylist structurally cannot cover ────────────────────────

def test_a_field_nobody_has_considered_is_refused():
    """The whole point. `internal_debug_state` is on no denylist anywhere,
    which is exactly why a denylist would have shipped it."""
    with pytest.raises(DTO.AudienceViolation) as exc:
        DTO.candidate_safe({"finished": False, "internal_debug_state": "x"})
    assert "internal_debug_state" in str(exc.value)
    assert "allowlist" in str(exc.value).lower()


def test_the_new_fields_added_this_week_would_not_have_leaked():
    """Concretely: recording lifecycle and transcript provenance both added
    recruiter-facing fields, and none of them is on the denylist."""
    for field in ("asr_adapter", "transcript_provenance", "authority",
                  "recording_completeness", "asr_confidence", "storage_ref",
                  "parts_expected", "lost_parts"):
        assert field not in DTO.FORBIDDEN_KEYS, (
            f"{field} is on the denylist; pick a field that genuinely is not, "
            f"or this test proves nothing")
        with pytest.raises(DTO.AudienceViolation):
            DTO.candidate_safe({"finished": False, field: "anything"})


def test_refusal_reaches_arbitrary_depth():
    with pytest.raises(DTO.AudienceViolation) as exc:
        DTO.candidate_safe(
            {"finished": False, "question": {"id": "q", "secret_rubric": 1}})
    assert "question.secret_rubric" in str(exc.value)


def test_refusal_reaches_inside_lists():
    with pytest.raises(DTO.AudienceViolation) as exc:
        DTO.candidate_safe({"finished": False,
                            "question": [{"id": "q"}, {"leaked": 2}]})
    assert "leaked" in str(exc.value)


def test_it_refuses_rather_than_silently_dropping():
    """Dropping would turn a disclosure bug into a missing-field bug, which is
    better, but it would also hide the mistake from the person making it."""
    with pytest.raises(DTO.AudienceViolation):
        DTO.candidate_safe({"finished": True, "probe_depth": 3})


# ── it must not break the payloads that are legitimate ────────────────────

def test_the_real_candidate_payloads_still_pass():
    assert DTO.candidate_safe({"finished": True,
                               "message": "That's everything — thank you."})
    assert DTO.candidate_safe({"finished": False, "waiting": True})
    assert DTO.candidate_safe(
        {"finished": False,
         "question": {"id": "q1", "text": "Tell me about a migration.",
                      "sequence": 3, "is_followup": True}})


def test_every_field_the_builders_emit_is_allowed():
    """The builders construct literal dicts, so they bypass the allowlist. If
    the two ever disagree, a legitimate payload starts failing in production
    and not here -- unless this test notices first."""
    class _Q:
        id, question_text, sequence_number, probe_depth = "q", "t", 1, 0
        question_kind = "OPENER"

    class _A:
        id = "a"

    class _I:
        id = "i"

    for built in (DTO.candidate_question(_Q()),
                  DTO.candidate_answer_ack(_A()),
                  DTO.candidate_state(interview=_I(), job_title="Engineer",
                                      questions_answered=2, finished=False)):
        unknown = set(built) - DTO.CANDIDATE_ALLOWED_KEYS
        assert not unknown, f"builder emits keys the allowlist refuses: {unknown}"


# ── the two lists must not contradict each other ──────────────────────────

def test_allowed_and_forbidden_are_disjoint():
    """A name on both lists would make the two controls disagree about the
    same field. Asserted at import too, so it cannot ship."""
    assert not (DTO.CANDIDATE_ALLOWED_KEYS & DTO.FORBIDDEN_KEYS)


# ── control: the two halves catch different things ────────────────────────

def test_control_the_two_controls_are_not_redundant():
    """If the allowlist were doing all the work, the denylist would be dead
    weight and the reverse. Each must catch something the other cannot.

    The denylist covers the explicitly-built DTOs, which never pass through the
    allowlist; the allowlist covers unknown names, which the denylist cannot
    enumerate. This asserts the second half concretely.
    """
    # allowlist catches what the denylist does not know about
    assert "internal_debug_state" not in DTO.FORBIDDEN_KEYS
    with pytest.raises(DTO.AudienceViolation):
        DTO.candidate_safe({"internal_debug_state": 1})

    # and the denylist is still the thing that names WHY, for known fields
    with pytest.raises(DTO.AudienceViolation) as exc:
        DTO._assert_clean({"probe_depth": 2})
    assert "recruiter-only" in str(exc.value)
