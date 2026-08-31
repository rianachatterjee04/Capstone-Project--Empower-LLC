"""Positive controls on the scoring instrument, and the fairness properties.

WHY THESE ARE PLANTED-DEFECT TESTS
"A score was produced" is not evidence that scoring works. Every one of these
changes ONE thing and asserts the score moves in the required direction -- or
required not to move. A scorer that returned 2.5 for everything would satisfy
"it produced a score" and fail every test in this file.

The six controls, from the specification:

  stronger evidence      -> the competency improves
  evidence removed       -> score or confidence falls
  contradiction added    -> a contradiction appears
  name changed only      -> substantive score unchanged
  appearance changed     -> competency score unchanged
  required not probed    -> completeness gate fails

The last three are fairness controls. They are cheap to pass HERE because
appearance and identity are not reachable from `scoring.py` at all -- and that
is the point: the design makes them unreachable, and these tests prove the
design holds rather than trusting it.
"""
from __future__ import annotations

import pytest

from app.interview import analysis as A
from app.interview import claims as C
from app.interview import evidence as E
from app.interview import scoring as S
from app.interview.planner import build_plan
from app.interview.rubrics import rubric_for_title


class _Planned:
    """Minimal stand-in for a persisted planned competency."""

    def __init__(self, key, required=True, weight=1.0, min_evidence=1):
        self.competency_key = key
        self.is_required = required
        self.role_weight = weight
        self.min_evidence_count = min_evidence
        self.evidence_needed = "a specific example with the candidate's part in it"


STRONG = (
    "I rewrote the settlement reconciler. Before that we were failing about 4% "
    "of settlements a day, mostly duplicate submissions after a timeout. I "
    "added an idempotency key and changed the retry to check state first. Over "
    "the following quarter that dropped to 0.2%. We knew it was the change "
    "because we held volume constant. The downside is the ledger write got "
    "slower, which we accepted instead of caching because stale reads would be "
    "worse. In hindsight I underestimated the migration effort.")

WEAK = ("I always try to make sure the team is aligned and we deliver value. "
        "My approach is to focus on communication and clear goals.")

MEDIUM = ("I worked on the Ledger migration with two other engineers. I owned "
          "the reconciler piece and rewrote how retries worked.")


def _score(text: str, *, key: str = "technical_depth",
           prior_claims=(), min_evidence: int = 1) -> S.Assessment:
    an = A.analyse(text, prior_claims=prior_claims,
                   expects_metric=True, expects_tradeoff=True)
    evs = E.extract(text, an, competency_key=key)
    for i, e in enumerate(evs):
        e.id = f"ev-{i}"
    return S.assess_competency(key, evs, min_evidence=min_evidence,
                               evidence_needed="a specific example")


# ===========================================================================
# 1. Stronger evidence raises the competency
# ===========================================================================

def test_a_stronger_answer_scores_higher_than_a_weaker_one():
    strong, medium, weak = _score(STRONG), _score(MEDIUM), _score(WEAK)

    assert strong.state == S.SCORED
    assert weak.state == S.INSUFFICIENT_EVIDENCE, (
        "a vague answer must not receive a score at all; a low score implies "
        "the interview established something about the candidate")

    assert medium.state == S.SCORED
    assert strong.score > medium.score, (
        f"the detailed, measured, reflective answer scored {strong.score} and "
        f"the thin one {medium.score}; the instrument is not discriminating")


def test_adding_a_measured_outcome_raises_the_score():
    """One controlled change: the same answer, plus a supported number."""
    base = ("I rewrote the settlement reconciler. I added an idempotency key "
            "and changed the retry to check state first.")
    plus = base + (" Before that we were failing 4% of settlements a day; over "
                   "the following quarter that dropped to 0.2%, and we knew it "
                   "was the change because we held volume constant.")

    a, b = _score(base), _score(plus)
    assert b.score > a.score, (
        f"adding a baseline, a period and an attribution moved the score from "
        f"{a.score} to {b.score}")
    assert b.confidence > a.confidence


# ===========================================================================
# 2. Removing evidence lowers score or confidence
# ===========================================================================

def test_removing_evidence_lowers_the_result():
    full = _score(STRONG)

    an = A.analyse(STRONG, expects_metric=True, expects_tradeoff=True)
    evs = E.extract(STRONG, an, competency_key="technical_depth")
    for i, e in enumerate(evs):
        e.id = f"ev-{i}"

    # Drop the strongest supporting item and re-assess. Nothing else changes.
    supporting = [e for e in evs if e.polarity == "SUPPORTS"]
    assert len(supporting) >= 3
    reduced = [e for e in evs if e is not supporting[0]]

    after = S.assess_competency("technical_depth", reduced, min_evidence=1,
                                evidence_needed="a specific example")
    assert (after.score < full.score) or (after.confidence < full.confidence), (
        f"removing an evidence item changed nothing: {full.score}/"
        f"{full.confidence} -> {after.score}/{after.confidence}. The score is "
        f"not a function of the evidence.")


def test_evidence_that_is_all_contradicting_yields_insufficient_not_zero():
    """Distinct from NOT_PROBED: the candidate WAS asked and did answer, and
    nothing they said supported the competency. That is still not a score of
    zero -- zero would be a finding, and what happened is an absence."""
    an = A.analyse(WEAK)
    evs = E.extract(WEAK, an, competency_key="technical_depth")
    assert evs, "the weak answer should still produce contradicting evidence"
    assert all(e.polarity != "SUPPORTS" for e in evs)
    a = S.assess_competency("technical_depth", evs, min_evidence=1)
    assert a.state == S.INSUFFICIENT_EVIDENCE
    assert a.score is None, (
        "with no supporting evidence the answer is INSUFFICIENT_EVIDENCE, not "
        "a score of zero; zero is a finding about the candidate")


# ===========================================================================
# 3. A contradiction surfaces
# ===========================================================================

def test_a_contradicting_answer_produces_a_contradiction():
    claim = C.Claim(
        claim_type=C.LEADERSHIP, claim_text="Managed a team of 12 engineers",
        subject="engineers", quantity_value=12.0, quantity_unit="engineers",
        source_kind=C.RESUME, source_ref="r.txt",
        source_excerpt="Managed a team of 12 engineers",
        source_span_start=0, source_span_end=30)

    answer = ("I had 3 engineers reporting to me directly at that point.")
    an = A.analyse(answer, prior_claims=[claim])

    assert an.contradicts, (
        "a resume claim of 12 and an answer of 3 on the same subject should "
        "be surfaced for clarification")

    evs = E.extract(answer, an, competency_key="ownership")
    kinds = {e.evidence_kind for e in evs}
    assert "CONTRADICTION" in kinds
    contradiction = next(e for e in evs if e.evidence_kind == "CONTRADICTION")
    assert contradiction.polarity == "CONTRADICTS"
    # Tone matters: this is a thing to resolve, not an accusation.
    assert "dishonesty" in contradiction.rationale or "not as dishonesty" \
        in contradiction.rationale


def test_a_consistent_restatement_is_not_a_contradiction():
    """Negative control. Without it, a detector that flagged everything would
    pass the test above."""
    claim = C.Claim(
        claim_type=C.LEADERSHIP, claim_text="Managed a team of 12 engineers",
        subject="engineers", quantity_value=12.0, quantity_unit="engineers",
        source_kind=C.RESUME, source_ref="r.txt",
        source_excerpt="Managed a team of 12 engineers")

    an = A.analyse("There were 12 engineers on that team.", prior_claims=[claim])
    assert not an.contradicts, (
        "restating the same number was flagged as a contradiction; false "
        "contradictions get put to candidates as though their resume is wrong")


# ===========================================================================
# 4. Identity does not move the score
# ===========================================================================

@pytest.mark.parametrize("name", [
    "James Sullivan", "Rajesh Patel", "Aisha Okonkwo", "Mei-Ling Chen",
    "Bartholomew Fotheringay-Smythe",
])
def test_the_candidate_name_does_not_change_the_score(name):
    """The name is not reachable from scoring. This proves it stays that way."""
    baseline = _score(STRONG)
    with_name = _score(f"{name} speaking. " + STRONG)

    assert with_name.state == baseline.state
    assert with_name.score == baseline.score, (
        f"prefixing the answer with {name!r} changed the score from "
        f"{baseline.score} to {with_name.score}")


def test_the_name_does_not_change_the_interview_plan():
    resume = ("Reduced settlement failures by 40% during the Ledger migration. "
              "Managed a team of 12 engineers. 8 years of distributed systems "
              "experience.")
    claims = C.extract_deterministic(resume, source_kind=C.RESUME,
                                     source_ref="r.txt")
    one = build_plan(job_title="Senior Software Engineer", candidate_claims=claims)

    named = "Aisha Okonkwo\n" + resume
    claims2 = C.extract_deterministic(named, source_kind=C.RESUME,
                                      source_ref="r.txt")
    two = build_plan(job_title="Senior Software Engineer", candidate_claims=claims2)

    assert one.question_texts() == two.question_texts(), (
        "adding a name to the resume changed the questions asked")


def test_appearance_cannot_reach_the_score():
    """Same transcript, different video. The score must be identical.

    It is identical because `scoring.py` consumes evidence rows and
    `evidence.py` emits only quotes -- there is no path from a frame to a
    number. This asserts that no such path is added later.
    """
    import inspect
    from tests._source_scan import code_only, mentions

    banned = ("video", "frame", "face", "facial", "emotion", "appearance",
              "attractive", "expression", "gaze", "smile",
              "accent", "pitch", "age", "gender", "race",
              "ethnicity", "disability")

    for module in (S, E):
        # CODE only. These modules' docstrings discuss at length what they
        # refuse to look at, and a naive scan matches the explanation.
        code = code_only(inspect.getsource(module))
        hits = [w for w in banned if mentions(code, w)]
        assert not hits, (
            f"{module.__name__} references {hits} in executable code; scoring "
            f"must not be able to see anything but the candidate's words")


# ===========================================================================
# 5. The completeness gate
# ===========================================================================

def test_an_unprobed_required_competency_fails_completeness():
    planned = [_Planned("technical_depth"), _Planned("safety_judgement")]
    an = A.analyse(STRONG, expects_metric=True)
    evs = E.extract(STRONG, an, competency_key="technical_depth")
    for i, e in enumerate(evs):
        e.id = f"ev-{i}"

    card = S.build_scorecard(
        rubric_key="software_engineer", rubric_version="test",
        planned=planned,
        evidence_by_competency={"technical_depth": evs})   # safety never probed

    assert card.completeness_state == S.INCOMPLETE
    assert "safety_judgement" in card.uncovered_required
    # And the gap must not be silently absorbed into the headline number.
    assert card.overall_score is not None
    assert card.overall_confidence < 0.95


def test_a_fully_probed_interview_is_complete():
    """Positive control for the gate."""
    planned = [_Planned("technical_depth"), _Planned("ownership")]
    an = A.analyse(STRONG, expects_metric=True, expects_tradeoff=True)

    by_key = {}
    for key in ("technical_depth", "ownership"):
        evs = E.extract(STRONG, an, competency_key=key)
        for i, e in enumerate(evs):
            e.id = f"{key}-{i}"
        by_key[key] = evs

    card = S.build_scorecard(rubric_key="software_engineer",
                             rubric_version="test", planned=planned,
                             evidence_by_competency=by_key)
    assert card.completeness_state == S.COMPLETE
    assert card.uncovered_required == []


def test_a_scorecard_is_always_decision_support():
    card = S.build_scorecard(rubric_key="x", rubric_version="v",
                             planned=[_Planned("k")],
                             evidence_by_competency={})
    assert card.decision_authority == "RECRUITER_DECISION_SUPPORT"
    assert card.overall_state == S.INSUFFICIENT_EVIDENCE
    assert card.overall_score is None


# ===========================================================================
# 6. Probing behaviour
# ===========================================================================

def test_a_strong_answer_is_not_probed_as_hard_as_a_weak_one():
    """The 'move on' property. A candidate who answers fully must not be
    interrogated -- redundant probes make a competency look thoroughly
    explored when it was answered once."""
    from app.interview import followup as F

    strong_an = A.analyse(STRONG, expects_metric=True, expects_tradeoff=True)
    weak_an = A.analyse(WEAK)

    strong_d = F.decide(strong_an, probe_depth=1, max_probe_depth=3,
                        evidence_count=5, min_evidence=1)
    weak_d = F.decide(weak_an, probe_depth=1, max_probe_depth=3,
                      evidence_count=0, min_evidence=1)

    assert len(strong_an.gaps) < len(weak_an.gaps), (
        f"the strong answer left {len(strong_an.gaps)} gaps and the weak one "
        f"{len(weak_an.gaps)}")
    assert weak_d.has_followup, "a vague answer must be probed"


def test_a_non_answer_gets_one_re_ask_and_then_moves_on():
    """Pressing someone who declined is not assessment."""
    from app.interview import followup as F

    an = A.analyse("pass")
    assert not an.is_substantive

    first = F.decide(an, probe_depth=0, max_probe_depth=3,
                     evidence_count=0, min_evidence=1)
    assert first.has_followup, "a non-answer deserves one gentle re-entry"

    second = F.decide(an, probe_depth=1, max_probe_depth=3,
                      evidence_count=0, min_evidence=1)
    assert not second.has_followup
    assert second.move_on


def test_no_acknowledgement_tells_the_candidate_how_they_are_doing():
    """Mid-interview evaluative feedback is both unfair and informative in the
    wrong way -- a candidate who hears "great answer" reads the next question
    differently."""
    from app.interview import followup as F
    import inspect

    from tests._source_scan import code_only

    # The STRINGS are what the candidate hears, so unlike the scan above this
    # one must look at literals -- but not at comments or docstrings, where
    # the module explains why it avoids exactly these phrases.
    src = inspect.getsource(F)
    code = code_only(src)          # identifiers only
    literals = "\n".join(
        line for line in src.splitlines()
        if not line.lstrip().startswith("#"))
    # Drop the module and function docstrings by removing triple-quoted blocks.
    import re as _re
    literals = _re.sub(r'"""(?:.|\n)*?"""', " ", literals)

    for phrase in ("great answer", "excellent", "well done", "perfect",
                   "that's impressive", "good job", "nice work",
                   "fantastic", "brilliant"):
        assert phrase not in literals.lower(), (
            f"the interviewer says {phrase!r} to the candidate, which tells "
            f"them how they are scoring mid-interview")
        assert phrase.replace(" ", "_") not in code.lower()


# ===========================================================================
# 7. The interviewer does not repeat itself
# ===========================================================================

def test_the_same_probe_is_not_generated_twice_for_the_same_answer():
    """Found by watching the demo, not by reasoning about the code.

    A candidate who repeats themselves produces the same analysis, which
    produces the same gaps, which produces the same probe. Asking it again
    gathers nothing and makes the interviewer look like it is not listening.
    `runner.next_question` suppresses a probe whose exact text has already
    been asked and moves to the next competency instead.

    This asserts the underlying determinism the suppression relies on: the
    same answer really does produce the same probe text, so comparing text is
    a sound way to detect the repeat.
    """
    from app.interview import followup as F

    an1 = A.analyse(WEAK)
    an2 = A.analyse(WEAK)
    d1 = F.decide(an1, probe_depth=1, max_probe_depth=3,
                  evidence_count=0, min_evidence=1)
    d2 = F.decide(an2, probe_depth=1, max_probe_depth=3,
                  evidence_count=0, min_evidence=1)

    assert d1.has_followup and d2.has_followup
    assert d1.followup.question_text == d2.followup.question_text, (
        "the same answer produced two different probes; the duplicate "
        "suppression in runner.next_question compares question text and would "
        "not catch a repeat")


def test_a_deeper_answer_produces_a_different_probe():
    """Positive control. If every answer produced the same probe text, the
    suppression above would end interviews after one follow-up."""
    from app.interview import followup as F

    vague = F.decide(A.analyse(WEAK), probe_depth=0, max_probe_depth=3,
                     evidence_count=0, min_evidence=1)
    owned = F.decide(
        A.analyse("We shipped the migration together and it went well.",
                  expects_ownership=True),
        probe_depth=0, max_probe_depth=3, evidence_count=0, min_evidence=1)

    assert vague.has_followup and owned.has_followup
    assert vague.followup.question_kind != owned.followup.question_kind, (
        "a vague answer and a team-voice answer produced the same kind of "
        "probe; the engine is not responding to what the answer contained")


# ===========================================================================
# 8. The instrument must not be biased toward one kind of work
# ===========================================================================
# Found by running a CDL driver through the interviewer. His answers were
# concrete, first-person and detailed, and he scored 0.79/4.

DRIVER_ANSWER = (
    "I had a reefer unit fail outside Joplin with 42,000 pounds of lettuce. I "
    "pulled the temperature log off the unit, photographed the readout, called "
    "dispatch and the after-hours line at the customer, and got to a repair "
    "shop within about ninety minutes. Product held at 38 degrees the whole "
    "time so the load was accepted.")

ENGINEER_ANSWER = (
    "I had a consumer fail in the Joplin region with 42,000 queued messages. I "
    "pulled the offset log off the broker, captured the readout, paged the "
    "on-call and the customer's escalation line, and shipped a fix within "
    "about ninety minutes. Lag held at 38 seconds the whole time so no data "
    "was lost.")


def test_ownership_is_detected_outside_software_vocabulary():
    """The verb list was `built|shipped|debugged|migrated|...`.

    A driver saying "I pulled the temperature log, photographed the readout
    and called dispatch" scored as NOT owning their work, because none of
    those verbs was on the list. That marks down every candidate whose job is
    not writing software, which is a fairness defect rather than a tuning
    problem.
    """
    an = A.analyse(DRIVER_ANSWER)
    assert an.has_first_person_action, (
        "first-person action was not detected in an answer that says 'I "
        "pulled', 'I called' and 'I got'")
    assert an.ownership_is_clear


def test_two_structurally_identical_answers_score_the_same_across_domains():
    """The control. The same sentence structure, one in freight and one in
    software, must produce the same assessment -- otherwise the instrument is
    scoring domain vocabulary."""
    driver = _score(DRIVER_ANSWER, key="exception_handling")
    engineer = _score(ENGINEER_ANSWER, key="exception_handling")

    assert driver.state == engineer.state
    assert driver.score == engineer.score, (
        f"the freight answer scored {driver.score} and the structurally "
        f"identical software answer scored {engineer.score}")


def test_a_descriptive_quantity_is_not_an_unsupported_metric():
    """"42,000 pounds of lettuce" and "38 degrees" describe the load. They are
    not performance claims, and demanding a baseline for them turned a precise
    answer into three probes and a CONTRADICTS finding."""
    an = A.analyse(DRIVER_ANSWER)
    assert an.has_number, "the answer plainly contains numbers"
    assert not an.has_outcome_number, (
        "descriptive quantities were read as performance claims")

    kinds = {e.evidence_kind for e in E.extract(
        DRIVER_ANSWER, an, competency_key="exception_handling")}
    assert "UNSUPPORTED_METRIC" not in kinds


def test_a_real_performance_claim_still_needs_its_baseline():
    """Positive control. The fix must not switch the metric check off."""
    claim = ("We improved on-time delivery to 98% after I rebuilt the check "
             "call process.")
    an = A.analyse(claim)
    assert an.has_outcome_number, (
        "'improved ... to 98%' is a performance claim and must still be "
        "treated as one")
    assert not an.quantitative_claim_is_supported, (
        "a percentage with no baseline and no period must still be flagged")


# ===========================================================================
# 9. Two mutation survivors, closed
# ===========================================================================

def test_contradicting_evidence_lowers_the_score():
    """Mutation survivor: removing the negative term from the score changed
    nothing any test could see.

    Contradicting evidence has to cost something, or the "contradictions"
    section of the debrief is decoration -- a recruiter would see a flagged
    contradiction sitting next to an unaffected score.
    """
    supporting = E.ExtractedEvidence(
        competency_key="k", polarity="SUPPORTS",
        evidence_kind="SPECIFIC_EXAMPLE", quote="q",
        rationale="r", strength=0.8)
    supporting.id = "s1"
    second = E.ExtractedEvidence(
        competency_key="k", polarity="SUPPORTS",
        evidence_kind="OWNERSHIP", quote="q2", rationale="r", strength=0.8)
    second.id = "s2"
    contradicting = E.ExtractedEvidence(
        competency_key="k", polarity="CONTRADICTS",
        evidence_kind="CONTRADICTION", quote="q3", rationale="r", strength=0.9)
    contradicting.id = "c1"

    clean = S.assess_competency("k", [supporting, second], min_evidence=1)
    with_contradiction = S.assess_competency(
        "k", [supporting, second, contradicting], min_evidence=1)

    assert clean.state == S.SCORED and with_contradiction.state == S.SCORED
    assert with_contradiction.score < clean.score, (
        f"adding a contradiction left the score at {clean.score}. The "
        f"contradictions section of the debrief would then sit next to a "
        f"score it did not affect.")
    assert with_contradiction.confidence < clean.confidence


def test_config_may_make_an_optional_competency_optional():
    """The capability that makes the rubric guard reachable."""
    from app.interview.rubrics import rubric_for_title

    rubric = rubric_for_title("Senior Software Engineer")
    optional_key = next(c.key for c in rubric.competencies if not c.required)

    plan = build_plan(job_title="Senior Software Engineer", candidate_claims=[],
                      role_config={"optional_competencies": [optional_key]})
    comp = next(c for c in plan.competencies
                if c.competency_key == optional_key)
    assert comp.is_required is False


def test_config_cannot_make_a_rubric_required_competency_optional():
    """Mutation survivor: the guard was unreachable, because nothing could set
    is_required=False. Now that `optional_competencies` can, the guard is what
    stops a role quietly ceasing to be assessed on the thing that matters."""
    from app.interview.rubrics import rubric_for_title

    rubric = rubric_for_title("CDL Driver")
    required_key = rubric.required_keys()[0]

    plan = build_plan(job_title="CDL Driver", candidate_claims=[],
                      role_config={"optional_competencies": [required_key]})
    comp = next(c for c in plan.competencies
                if c.competency_key == required_key)
    assert comp.is_required is True, (
        f"role config made rubric-required {required_key!r} optional")
    assert "rubric marks it required" in comp.why_it_matters, (
        "the override happened silently; a hiring manager who asked for this "
        "should be able to see that it was refused")


# ===========================================================================
# Finance is one of the buyers, and got the blandest interview in the set
# ===========================================================================

def test_a_finance_title_gets_a_finance_rubric():
    """A staff accountant used to fall through to GENERAL and be asked to
    "pick one thing from the last year you'd point to as your best work" -- a
    question that would suit a marketer, a nurse or a bricklayer equally well.
    Reviewed against a CDL driver, a dispatcher and a broker, all of whom got
    real domain questions, it was plainly the weakest interview in the set.
    """
    from app.interview import rubrics as RB

    for title in ("Staff Accountant", "Controller", "Bookkeeper",
                  "Senior Accounting Manager", "Financial Analyst",
                  "Finance Manager"):
        assert RB.rubric_for_title(title).key == "accountant", title


def test_account_manager_is_not_an_accountant():
    """The obvious false match, and a sales job. Getting this wrong would
    interview a salesperson on reconciliations, which is worse than generic --
    the scorecard would look specific and be about the wrong role."""
    from app.interview import rubrics as RB
    assert RB.rubric_for_title("Account Manager").key != "accountant"
    assert RB.rubric_for_title("Key Account Executive").key != "accountant"


def test_the_finance_rubric_asks_for_evidence_a_bluffer_cannot_produce():
    """Each competency has to name something a real accountant can point at.
    "Tell me about your strengths" is answerable by anyone; "an account that
    would not reconcile, and what the difference turned out to be" is not."""
    from app.interview import rubrics as RB

    r = RB.RUBRICS["accountant"]
    keys = {c.key for c in r.competencies}
    assert {"close_and_reconciliation", "controls_and_judgement",
            "audit_and_evidence"} <= keys

    for c in r.competencies:
        if c.key in ("close_and_reconciliation", "controls_and_judgement",
                     "audit_and_evidence"):
            assert c.evidence_needed and len(c.evidence_needed) > 30, (
                f"{c.key} does not say what evidence would satisfy it")
            assert c.generic_question.strip().endswith("?"), c.key


def test_the_finance_interview_is_not_the_general_one_with_a_new_name():
    """The control. Adding a rubric that reuses the generic questions would
    pass every test above and change nothing a candidate experiences."""
    from app.interview import rubrics as RB

    acct = {c.generic_question for c in RB.RUBRICS["accountant"].competencies}
    generic = {c.generic_question for c in RB.RUBRICS["general"].competencies}
    new = acct - generic
    assert len(new) >= 3, (
        f"only {len(new)} of the accountant's questions differ from the "
        f"general rubric's; it is the same interview with a new label")
    joined = " ".join(new).lower()
    for word in ("reconcile", "accounting treatment", "auditor"):
        assert word in joined, f"no finance question mentions {word!r}"
