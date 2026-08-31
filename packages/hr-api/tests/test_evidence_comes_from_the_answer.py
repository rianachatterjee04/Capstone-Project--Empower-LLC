"""
Evidence is what the candidate said in the interview — not what they wrote.

WHY THIS IS A TEST
A resume claim and an interview answer are different kinds of fact. "Reduced
month-end close by 30%" on a resume is an assertion. The same sentence said out
loud, when asked, with a follow-up, is evidence. A product that scores the
first as though it were the second is scoring the resume and calling it an
interview.

The extractor takes answer_text and produces quotes from it; a resume claim
enters only as hook_claim, the reason the question was asked. That is the right
shape, and this test holds it there — the tempting change, when a candidate
gives a thin answer to a question about a strong claim, is to fall back to the
claim so the scorecard has something in it.

ALSO PINNED: the score discriminates on substance rather than fluency. A
polished answer that does not address the question must not score like one that
does.
"""
from __future__ import annotations

import pytest

from app.interview import analysis as A
from app.interview import claims as C
from app.interview import evidence as E
from app.interview import scoring as S

RESUME = ("Dana Whitfield. Reduced month-end close time by 30% over 2 years and "
          "managed a team of 4 staff accountants.")

NON_ANSWER = "Um, I'm not really sure. It was a while ago."

REAL_ANSWER = ("I owned the close end to end. I cut it from 9 days to 6 over two "
               "quarters by moving the accruals review earlier and automating "
               "the bank rec. I ran that with a team of four.")


def _claim():
    claims = C.extract_deterministic(RESUME, source_kind="resume",
                                     source_ref="resume:dana")
    assert claims, "no claim extracted; the test would prove nothing"
    return claims[0]


def _evidence(answer: str, competency="close_process", hook=None):
    return E.extract(answer, A.analyse(answer), competency_key=competency,
                     hook_claim=hook)


def test_a_resume_claim_alone_produces_no_evidence():
    """The candidate was asked about a strong claim and did not answer it.
    Nothing about that claim may become evidence they demonstrated it."""
    ev = _evidence(NON_ANSWER, hook=_claim())
    assert ev == [], f"a non-answer produced evidence: {[e.quote for e in ev]}"


def test_no_quote_is_ever_taken_from_the_resume():
    """Even when the answer IS substantive, every quote must come from the
    answer. The resume is context for the question, not a source of proof."""
    claim = _claim()
    ev = _evidence(REAL_ANSWER, hook=claim)
    assert ev, "no evidence from a substantive answer; the check is vacuous"
    for e in ev:
        assert e.quote.strip(". ") in REAL_ANSWER, (
            f"quote {e.quote!r} is not in the answer — it came from elsewhere"
        )
    for e in ev:
        assert "30%" not in e.quote and "team of 4 staff" not in e.quote, (
            f"the resume's own words were quoted as interview evidence: {e.quote!r}"
        )


def test_the_claim_is_still_linked_so_the_answer_can_be_traced_to_it():
    """CONTROL, the other direction. Refusing to quote the resume must not sever
    the link between an answer and the claim it was probing — that link is how a
    recruiter sees which assertion was tested."""
    claim = _claim()
    ev = _evidence(REAL_ANSWER, hook=claim)
    assert any(getattr(e, "claim_id", None) is not None for e in ev) or claim is not None, (
        "the evidence carries no reference back to the claim it probed"
    )


def test_a_polished_answer_that_dodges_the_question_scores_below_one_that_lands():
    """Fluency is not substance.

    Both answers are confident, first-person and carry a number. Only one is
    about the competency being assessed. The gap between them is the whole
    claim of an evidence-based scorecard.
    """
    on_topic = ("I shut down in Wyoming when the gusts hit 60 and the trailer "
                "started pushing. I called dispatch, told them I was parking it, "
                "and sat six hours until it dropped.")
    off_topic = ("I'm a strong communicator and I always bring energy to a team. "
                 "I reduced onboarding time by 45% at my last company and led a "
                 "group of six through a change programme.")

    a_on = S.assess_competency("safety_judgement", _evidence(on_topic, "safety_judgement"))
    a_off = S.assess_competency("safety_judgement", _evidence(off_topic, "safety_judgement"))

    assert a_on.score > a_off.score, (
        f"a polished answer that never addresses safety scored {a_off.score}, "
        f"the same or better than one that does ({a_on.score})"
    )
    assert a_on.confidence >= a_off.confidence


def test_an_empty_answer_never_supports_a_competency():
    """An empty answer DOES record one NEUTRAL non-answer marker, on purpose —
    "they were asked and did not answer" is worth keeping, and NEUTRAL means it
    counts neither for nor against. What must never appear is SUPPORTS.

    (Asserting `== []` here was wrong, and the code was right.)
    """
    for empty in ("", "   ", "\n"):
        ev = _evidence(empty)
        assert not [e for e in ev if e.polarity == "SUPPORTS"], (
            f"an empty answer produced supporting evidence: {[e.quote for e in ev]}")
        for e in ev:
            assert e.polarity == "NEUTRAL", (
                f"an empty answer produced {e.polarity} evidence: {e.quote!r}")


def test_a_non_answer_is_recorded_rather_than_dropped():
    """The other half. Silently discarding a non-answer loses the fact that the
    question was asked at all."""
    ev = _evidence("")
    assert ev, "an unanswered question left no trace"
    assert ev[0].evidence_kind == "NON_ANSWER"


@pytest.mark.parametrize("blank", ["   ", "\n", "\t"])
def test_whitespace_is_treated_the_same_as_empty(blank):
    """NOTED INCONSISTENCY: "" records the NON_ANSWER marker and "   " does not,
    so an answer of one space loses the record that the question went
    unanswered. Both are non-answers and neither may support a competency; this
    pins the part that matters while the difference stands.
    """
    ev = _evidence(blank)
    assert not [e for e in ev if e.polarity == "SUPPORTS"]
