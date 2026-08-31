"""Does the score respond to what it claims to measure -- and only to that?

test_interview_fairness.py already checks DIRECTION on chosen examples: a
stronger answer scores higher, adding a measured outcome raises the score, the
candidate's name does not change it. Those are the right questions asked once
each.

This file asks them as LAWS, swept across many configurations, plus the ones an
example-based test cannot express:

  RESPONDS      monotone in supporting evidence, monotone (downward) in
                contradicting evidence, and sensitive to strength.
  DOES NOT      invariant to the ORDER evidence arrives in, to the competency's
  RESPOND       name, and to evidence ids -- none of which is a property of the
                candidate.
  COUPLES       a state that may not carry a score never carries one, and the
                score never leaves its declared range.

An instrument that moves with what it measures is only half the requirement.
One that ALSO moves with something it does not claim to measure is not
measuring the first thing.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

import pytest

from app.interview import scoring as S


@dataclass
class Ev:
    """Duck-typed to what assess_competency reads: polarity, evidence_kind,
    strength, id. The ORM row satisfies the same shape."""
    polarity: str
    evidence_kind: str
    strength: float = 1.0
    id: str = "e"


POS_KINDS = ["QUANTIFIED_OUTCOME", "TRADEOFF_REASONING", "OWNERSHIP",
             "SPECIFIC_EXAMPLE", "FAILURE_REFLECTION", "DOMAIN_DEPTH"]
NEG_KINDS = ["CONTRADICTION", "UNSUPPORTED_METRIC", "VAGUENESS"]


def sup(kind, strength=1.0, i="s"):
    return Ev("SUPPORTS", kind, strength, i)


def con(kind, strength=1.0, i="c"):
    return Ev("CONTRADICTS", kind, strength, i)


def score_of(evidence, **kw):
    a = S.assess_competency("exception_handling", evidence, **kw)
    return a.score


# ═══════════════════════════════════════════════════════════════════════
#  IT RESPONDS to what it claims to measure
# ═══════════════════════════════════════════════════════════════════════

def test_law_adding_supporting_evidence_never_lowers_the_score():
    """Swept, not sampled. One example passing says nothing about the curve
    around it, and the requirement-met floor is exactly the kind of special
    case that breaks monotonicity in one corner."""
    for combo in itertools.combinations(POS_KINDS, 2):
        base = [sup(k) for k in combo]
        before = score_of(base)
        for extra in POS_KINDS:
            after = score_of(base + [sup(extra)])
            assert after >= before, (
                f"adding {extra} to {combo} LOWERED the score "
                f"{before} -> {after}")


def test_law_adding_contradicting_evidence_never_raises_the_score():
    for combo in itertools.combinations(POS_KINDS, 3):
        base = [sup(k) for k in combo]
        before = score_of(base)
        for bad in NEG_KINDS:
            after = score_of(base + [con(bad)])
            assert after <= before, (
                f"adding a {bad} to {combo} RAISED the score "
                f"{before} -> {after}")


def test_law_more_strength_never_scores_lower():
    for kind in POS_KINDS:
        prev = -1.0
        for strength in (0.2, 0.4, 0.6, 0.8, 1.0):
            s = score_of([sup(kind, strength), sup("OWNERSHIP", strength)])
            assert s >= prev, f"{kind} at strength {strength} dipped"
            prev = s


def test_distinct_kinds_beat_repetition_of_one():
    """The docstring's claim, made checkable: three specific examples are
    better than one, but not three times better, and repeating yourself is not
    rewarded like breadth."""
    three_same = score_of([sup("SPECIFIC_EXAMPLE", i=str(n)) for n in range(3)])
    three_diff = score_of([sup("SPECIFIC_EXAMPLE"), sup("OWNERSHIP"),
                           sup("QUANTIFIED_OUTCOME")])
    one = score_of([sup("SPECIFIC_EXAMPLE")])

    assert three_diff > three_same, "breadth must beat repetition"
    assert three_same > one, "more evidence should still count for something"
    assert three_same < one * 3, "repetition must not scale linearly"


# ═══════════════════════════════════════════════════════════════════════
#  IT DOES NOT RESPOND to what is not a property of the candidate
# ═══════════════════════════════════════════════════════════════════════

def test_law_the_order_evidence_arrives_in_does_not_change_the_score():
    """The order answers happen to come back in is a property of the
    conversation, not of the candidate. A score that moves with it is reading
    the interview's shape, not the person's."""
    ev = [sup("QUANTIFIED_OUTCOME", 0.9), sup("OWNERSHIP", 0.7),
          sup("SPECIFIC_EXAMPLE", 1.0), con("VAGUENESS", 0.5)]
    reference = score_of(ev)
    rng = random.Random(20260830)
    for _ in range(40):
        shuffled = ev[:]
        rng.shuffle(shuffled)
        assert score_of(shuffled) == reference, (
            f"score moved with evidence ORDER: {reference} vs "
            f"{score_of(shuffled)} for {[e.evidence_kind for e in shuffled]}")


def test_law_the_competency_name_does_not_change_the_score():
    ev = [sup("QUANTIFIED_OUTCOME"), sup("OWNERSHIP")]
    scores = {S.assess_competency(name, ev).score
              for name in ("exception_handling", "safety_judgement",
                           "communication", "zzz_unknown_competency", "")}
    assert len(scores) == 1, f"the competency's NAME moved the score: {scores}"


def test_law_evidence_ids_do_not_change_the_score():
    a = score_of([sup("OWNERSHIP", i="aaa"), sup("DOMAIN_DEPTH", i="bbb")])
    b = score_of([sup("OWNERSHIP", i="zzz"), sup("DOMAIN_DEPTH", i="000")])
    assert a == b


# ═══════════════════════════════════════════════════════════════════════
#  STATE AND SCORE STAY COUPLED
# ═══════════════════════════════════════════════════════════════════════

def test_a_state_that_may_not_carry_a_score_never_carries_one():
    """The module's own claim: "state INSUFFICIENT_EVIDENCE cannot carry a
    score, so no downstream code can average one in by accident"."""
    cases = [
        ([], "nothing at all"),
        ([Ev("NEUTRAL", "NON_ANSWER")], "a non-answer"),
        ([con("CONTRADICTION")], "only contradictions"),
    ]
    for ev, why in cases:
        a = S.assess_competency("exception_handling", ev)
        assert a.state in (S.NOT_PROBED, S.INSUFFICIENT_EVIDENCE), why
        assert a.score is None, (
            f"{why} produced state {a.state} carrying score {a.score}. A "
            f"downstream average would silently include it.")


def test_a_non_answer_is_absence_of_evidence_not_evidence_of_weakness():
    """The fairness property that matters most: refusing to answer must not
    read as scoring zero, because zero is a claim about the candidate."""
    # NEUTRAL is the polarity app.interview.evidence actually assigns; a
    # non-answer is neither for nor against the candidate, which is the whole
    # point of the state it produces.
    a = S.assess_competency("exception_handling", [Ev("NEUTRAL", "NON_ANSWER")])
    assert a.state == S.INSUFFICIENT_EVIDENCE
    assert a.score is None
    assert "absence of evidence" in a.rationale


def test_the_score_never_leaves_its_declared_range():
    """Saturation, from both ends, with deliberately absurd input."""
    piles = [
        [sup(k, 1.0, str(n)) for n in range(30) for k in POS_KINDS],
        [con(k, 1.0, str(n)) for n in range(30) for k in NEG_KINDS]
        + [sup("OWNERSHIP")],
        [sup(k, 5.0) for k in POS_KINDS],          # strength out of band
    ]
    for ev in piles:
        a = S.assess_competency("exception_handling", ev)
        if a.score is not None:
            assert 0.0 <= a.score <= 4.0, f"score {a.score} left the scale"
            assert int(round(a.score)) in S.SCALE, "score has no band"
        if a.confidence is not None:
            assert 0.0 <= a.confidence <= 0.95


def test_confidence_measures_what_was_established_not_how_good_it_was():
    """Two candidates, same breadth of evidence, opposite quality. Confidence
    is about the INTERVIEW, so contradictions lower it -- what must not happen
    is confidence tracking the score upward as if certainty and merit were the
    same thing."""
    strong = S.assess_competency(
        "exception_handling",
        [sup("QUANTIFIED_OUTCOME"), sup("OWNERSHIP"), sup("DOMAIN_DEPTH")])
    contested = S.assess_competency(
        "exception_handling",
        [sup("QUANTIFIED_OUTCOME"), sup("OWNERSHIP"), sup("DOMAIN_DEPTH"),
         con("CONTRADICTION"), con("VAGUENESS")])

    assert contested.score < strong.score
    assert contested.confidence < strong.confidence, (
        "a contested account should leave us LESS certain of what was "
        "established, not more")


# ═══════════════════════════════════════════════════════════════════════
#  Control
# ═══════════════════════════════════════════════════════════════════════

def test_control_the_instrument_actually_discriminates():
    """If every input scored the same, every invariance law above would pass
    while the scorer reported nothing at all."""
    seen = {
        score_of([sup("SPECIFIC_EXAMPLE", 0.3)]),
        score_of([sup("QUANTIFIED_OUTCOME"), sup("OWNERSHIP")]),
        score_of([sup(k) for k in POS_KINDS]),
    }
    assert len(seen) >= 3, f"the scorer barely discriminates: {seen}"


# ═══════════════════════════════════════════════════════════════════════
#  Documented, not asserted-as-correct: an unweighted kind still counts
# ═══════════════════════════════════════════════════════════════════════

def test_an_unweighted_evidence_kind_contributes_at_the_default_weight():
    """PINNED BEHAVIOUR, flagged rather than changed.

    `_POSITIVE_WEIGHT.get(kind, 0.5)` means an evidence kind nobody has
    weighted still contributes 0.5 toward a hiring score. Adding an extractor
    that emits a new kind therefore moves scores immediately, without anyone
    deciding what that kind is worth -- the same fail-open shape as a denylist.

    This is NOT changed here: every weight change moves real scores, and that
    is a product decision rather than a test-driven one. It is pinned so the
    behaviour is visible and so a future change to it is deliberate.
    """
    known = score_of([sup("SPECIFIC_EXAMPLE")])
    unknown = score_of([sup("A_KIND_NOBODY_WEIGHTED")])
    assert unknown > 0, (
        "an unweighted kind contributes to the score at the 0.5 default")
    assert unknown != known, "and not at any deliberate weight"

    # The same default applies on the negative side.
    base = score_of([sup(k) for k in POS_KINDS[:3]])
    with_unknown_neg = score_of(
        [sup(k) for k in POS_KINDS[:3]] + [con("AN_UNWEIGHTED_PROBLEM")])
    assert with_unknown_neg < base
