"""The conversation itself, under test.

Every case here is a sentence that was actually generated and put to a
candidate, or a signal that was actually computed from an answer, before it
was fixed. They are in one file because they are one class of defect: the
interview was technically correct and read as though nothing had been written
for the person in the chair.

No database. These are the pure functions that decide what a candidate hears,
so they belong in the default gate rather than behind a PostgreSQL bootstrap.
"""
from __future__ import annotations

import pathlib

import re

import pytest

from app.interview import analysis as A
from app.interview import claims as C
from app.interview import followup as F
from app.interview import planner as P
from app.interview import rubrics as RB

DRIVER_RESUME = """Kenworth T680 / reefer, 6 years OTR and regional.
Class A CDL, clean MVR. Tanker endorsement.
Texas to the Midwest hauling refrigerated produce.
"""
DISPATCH_RESUME = """Dispatcher, 4 years at a 40-truck regional carrier.
Covered 60-80 loads a week across Texas and the Southeast.
Reduced empty miles by 18% by rebuilding the board around backhauls.
Managed 12 drivers day to day.
"""


def _claims(text: str):
    return C.extract_deterministic(text, source_kind="RESUME", source_ref="r")


def _plan(title: str, resume: str):
    return P.build_plan(job_title=title, candidate_claims=_claims(resume))


# ===========================================================================
# Reading the resume back to the candidate
# ===========================================================================

def test_a_tenure_subject_is_not_a_list():
    """"6 years OTR and regional" produced the subject "otr and regional",
    and the question read "You put 6 years in otr and regional." """
    tenure = [c for c in _claims(DRIVER_RESUME)
              if c.claim_type == C.DOMAIN_EXPERIENCE and c.is_quantified]
    assert tenure, "the resume says 6 years; something should have caught it"
    assert " and " not in (tenure[0].subject or "")


def test_a_tenure_subject_does_not_start_mid_phrase():
    """"4 years at a 40-truck regional carrier" produced "truck regional
    carrier" -- a phrase that begins inside a hyphenated compound."""
    tenure = [c for c in _claims(DISPATCH_RESUME)
              if c.claim_type == C.DOMAIN_EXPERIENCE and c.is_quantified]
    assert tenure
    assert tenure[0].subject == "regional carrier"


def test_an_acronym_is_read_back_in_its_own_casing():
    assert P.subject_phrase("otr") == "OTR work"
    assert P.subject_phrase("class a cdl").startswith("CDL") is False  # noqa
    assert "CDL" in P.subject_phrase("cdl")


def test_the_same_equipment_under_two_names_is_one_claim():
    """"refrigerated" and "reefer" are the same trailer. Extracting both let
    two competencies hook onto the same fact and ask about it twice."""
    kit = {c.claim_text for c in _claims(DRIVER_RESUME)
           if c.claim_type == C.EQUIPMENT_OPERATED}
    assert "reefer" in kit
    assert "refrigerated" not in kit


def test_no_generated_question_contains_a_mangled_phrase():
    """A grab-bag guard: nothing a candidate hears may contain a doubled
    space, a missing space after a number, or a lowercase acronym."""
    for title, resume in (("CDL Driver", DRIVER_RESUME),
                          ("Dispatcher", DISPATCH_RESUME)):
        for comp in _plan(title, resume).competencies:
            q = comp.initial_question
            assert "  " not in q, (title, q)
            assert not re.search(r"\d(?:years|days|loads)\b", q), (title, q)
            assert not re.search(r"\botr\b", q), (title, q)


# ===========================================================================
# Hooks have to serve the competency they were built for
# ===========================================================================

def test_equipment_experience_hooks_onto_the_equipment():
    """The rubric lists EQUIPMENT_OPERATED first for exactly this reason. The
    ranking ignored that order and picked the richest claim instead, so a
    driver whose resume said reefer six times was asked about lane types."""
    plan = _plan("CDL Driver", DRIVER_RESUME)
    q = plan.competencies[0].initial_question
    assert plan.competencies[0].competency_key == "equipment_experience"
    assert "reefer" in q.lower()


def test_a_bare_lane_mention_does_not_become_a_hook():
    """"You mention regional work. Walk me through the most difficult
    situation" was generated for TWO different competencies in one interview:
    one template, two nouns, neither serving the competency."""
    comp = RB.CDL_DRIVER.get("exception_handling")
    lane = C.Claim(claim_type=C.DOMAIN_EXPERIENCE, claim_text="regional",
                   subject="regional", source_kind="RESUME", source_ref="r",
                   source_excerpt="regional")
    assert P.question_from_claim(comp, lane) is None


def test_a_tenure_hook_still_asks_the_competencys_own_question():
    """Grounding must not replace the question. safety_judgement used to get
    "take the hardest single problem you hit in that time", losing the
    rubric's far better opener about deciding not to run."""
    plan = _plan("CDL Driver", DRIVER_RESUME)
    safety = [c for c in plan.competencies
              if c.competency_key == "safety_judgement"][0]
    assert "6 years" in safety.initial_question
    assert "decide not to run" in safety.initial_question


def test_a_metric_hook_does_not_hijack_a_non_metric_competency():
    """exception_handling -- "a specific load that went wrong, who was called,
    what it cost" -- was asked to explain the baseline and attribution behind
    an 18% empty-miles figure, because that was the claim left over."""
    plan = _plan("Dispatcher", DISPATCH_RESUME)
    exc = [c for c in plan.competencies
           if c.competency_key == "exception_handling"][0]
    assert "18%" in exc.initial_question or "18" in exc.initial_question
    assert "how did you establish that the improvement" not in \
        exc.initial_question.lower()
    assert "went badly wrong" in exc.initial_question.lower()


# ===========================================================================
# Role specificity
# ===========================================================================

def test_ownership_is_not_asked_in_identical_words_across_roles():
    """One shared frozen competency was reused by every rubric, so a CDL
    driver and a freight broker heard the same sentence."""
    asked = {r.key: r.get("ownership").generic_question
             for r in (RB.CDL_DRIVER, RB.DISPATCHER, RB.FREIGHT_BROKER)
             if r.get("ownership")}
    assert len(set(asked.values())) == len(asked), asked


def test_a_driver_is_never_asked_what_they_built():
    """"what did you personally decide, build or handle" went to a CDL
    driver. Nothing in that job is built."""
    lex = F.lexicon_for(RB.DOMAIN_DRIVER)
    assert "build" not in lex.did_verbs
    an = A.analyse("We handled it as a team and it worked out in the end.",
                   expects_ownership=True)
    probe = F.decide(an, probe_depth=0, max_probe_depth=3, evidence_count=0,
                     min_evidence=1, domain=RB.DOMAIN_DRIVER,
                     competency_key="ownership")
    assert probe.has_followup
    assert "build" not in probe.followup.question_text


def test_the_software_lexicon_still_says_build():
    """Positive control. A rule that stripped the word everywhere would pass
    the test above and make the software interview worse."""
    assert "build" in F.lexicon_for(RB.DOMAIN_SOFTWARE).did_verbs


# ===========================================================================
# Robotic repetition
# ===========================================================================

def test_the_interviewer_does_not_open_every_probe_with_the_same_word():
    """"Got it." was returned for every answer under 120 words. A ten-question
    interview opened nine probes identically."""
    an = A.analyse("We handled it as a team and it worked out in the end.",
                   expects_ownership=True)
    opens = set()
    for depth in range(3):
        for key in ("ownership", "communication", "problem_solving"):
            d = F.decide(an, probe_depth=depth, max_probe_depth=4,
                         evidence_count=0, min_evidence=1,
                         domain=RB.DOMAIN_FREIGHT_OFFICE, competency_key=key)
            if d.has_followup:
                opens.add(d.followup.question_text.split(".")[0])
    assert len(opens) >= 3, f"only {len(opens)} distinct openings: {opens}"


def test_the_acknowledgement_is_stable_across_processes():
    """Variety must not come from `hash()`, which is salted per process: the
    same interview would replay with different wording every time."""
    an = A.analyse("We handled it as a team and it worked out in the end.",
                   expects_ownership=True)
    first = [F.decide(an, probe_depth=0, max_probe_depth=3, evidence_count=0,
                      min_evidence=1, competency_key="ownership"
                      ).followup.question_text for _ in range(5)]
    assert len(set(first)) == 1


def test_a_probe_body_is_exposed_so_the_runner_can_deduplicate():
    """Varying the acknowledgement defeated the duplicate guard, which
    compared whole sentences -- so the same probe went out twice in a row."""
    an = A.analyse("We handled it as a team and it worked out in the end.",
                   expects_ownership=True)
    a = F.decide(an, probe_depth=0, max_probe_depth=3, evidence_count=0,
                 min_evidence=1, competency_key="ownership").followup
    b = F.decide(an, probe_depth=1, max_probe_depth=3, evidence_count=0,
                 min_evidence=1, competency_key="ownership").followup
    assert a.question_text != b.question_text, "the wording should vary"
    assert a.probe_body == b.probe_body, "the guard needs them to compare equal"


def test_no_probe_is_evaluative():
    an = A.analyse("We handled it as a team and it worked out in the end.",
                   expects_ownership=True)
    for depth in range(4):
        d = F.decide(an, probe_depth=depth, max_probe_depth=4,
                     evidence_count=0, min_evidence=1,
                     competency_key="ownership")
        if d.has_followup:
            low = d.followup.question_text.lower()
            for phrase in ("great", "excellent", "well done", "impressive"):
                assert phrase not in low


# ===========================================================================
# Signals that were wrong about the candidate
# ===========================================================================

@pytest.mark.parametrize("answer", [
    "The reefer failure. Nobody told me to pull the temperature log; I did it "
    "because it was the only thing that would stop the load being rejected.",
    "I rebuilt it around backhauls.",
    "I personally called the receiver the morning of.",
    "I never signed that BOL.",
    "I gave the keys back and walked.",
])
def test_a_first_person_action_is_recognised(answer):
    """"did" -- the most common past-tense verb in English -- was missing from
    the irregular list, so the clearest statement of ownership in the driver
    interview registered as none at all."""
    assert A.analyse(answer).has_first_person_action, answer


@pytest.mark.parametrize("answer", [
    "I think I generally did pretty well with the loads.",
    "I did well on that route.",
    "We handled it as a team.",
])
def test_an_empty_predicate_is_not_an_action(answer):
    """Negative control for the fix above. Admitting "did" must not admit
    "I did pretty well", which names nothing."""
    assert not A.analyse(answer).has_first_person_action, answer


def test_they_meaning_the_customer_is_not_team_voice():
    """"I call before they call me" -- where "they" is the CUSTOMER -- was
    recorded as speaking in the team's voice, and the candidate was then told
    "you've described what the team did"."""
    an = A.analyse("Telling a customer their load is going to be late is the "
                   "job. I call before they call me, with a new time I can "
                   "actually hit.")
    assert not an.team_voice_only


def test_real_team_voice_is_still_caught():
    """Positive control."""
    an = A.analyse("We rebuilt the whole board as a team and the numbers came "
                   "down. Our team handled all of it.")
    assert an.team_voice_only


def test_the_ownership_probe_does_not_invent_a_team():
    an = A.analyse("Telling a customer their load is late is the job. I call "
                   "before they call me.", expects_ownership=True)
    probe = F._ownership_probe(an, F.lexicon_for(RB.DOMAIN_FREIGHT_OFFICE), "x")
    assert "what the team did" not in probe.question_text


# ===========================================================================
# Numbers
# ===========================================================================

OPS_ANSWER = ("60 to 80 loads a week, 40 trucks, empty miles from 22% to 18% "
              "between Q2 and Q4.")


def test_a_fiscal_quarter_is_a_timeframe():
    assert A.analyse(OPS_ANSWER).has_timeframe


@pytest.mark.parametrize("answer", [
    "We ran it between Q2 and Q4.",
    "Over two quarters it came down.",
    "That was in March.",
    "It happened last summer.",
])
def test_operational_periods_are_recognised(answer):
    assert A.analyse(answer).has_timeframe, answer


def test_a_dense_numeric_answer_is_specific_without_proper_nouns():
    """An operations answer carries its specifics as numbers, not names. The
    25-word floor failed this at sixteen words and five quantities."""
    an = A.analyse(OPS_ANSWER)
    assert an.named_specifics == 0
    assert an.distinct_numbers >= 3
    assert an.is_specific


def test_a_supported_number_is_not_recorded_against_the_candidate():
    """This answer produced CONTRADICTS / UNSUPPORTED_METRIC -- the most
    precise answer in the interview became evidence against them."""
    from app.interview import evidence as E
    an = A.analyse(OPS_ANSWER)
    found = E.extract(OPS_ANSWER, an, competency_key="evidence_specificity")
    assert found
    assert not [e for e in found if e.evidence_kind == E.UNSUPPORTED_METRIC]
    assert [e for e in found if e.evidence_kind == E.QUANTIFIED_OUTCOME]


def test_an_actually_unsupported_number_is_still_caught():
    """Positive control for the fix above."""
    from app.interview import evidence as E
    text = "We improved on-time delivery by 30%."
    an = A.analyse(text)
    found = E.extract(text, an, competency_key="evidence_specificity")
    assert [e for e in found if e.evidence_kind == E.UNSUPPORTED_METRIC]


# ===========================================================================
# False contradictions
# ===========================================================================

def test_a_tenure_claim_is_not_contradicted_by_a_percentage():
    """The detector compared "4 years" against every bare number in the
    answer and told the candidate:

        resume says 4years for truck regional carrier; the answer says 22

    Four years against twenty-two percent, put to their face, on camera.
    """
    an = A.analyse(
        "We ran 40 trucks and the board was built by lane. I rebuilt it "
        "around backhauls, which took empty miles from about 22% down to 18% "
        "over two quarters.",
        prior_claims=_claims(DISPATCH_RESUME))
    assert an.contradicts == []


def test_a_real_numeric_disagreement_is_still_raised():
    """Positive control. A detector that never fires is not a safe detector,
    it is an absent one."""
    an = A.analyse("I had 3 drivers reporting to me directly.",
                   prior_claims=_claims(DISPATCH_RESUME))
    assert an.contradicts
    assert "12 drivers" in an.contradicts[0]


def test_a_loose_restatement_is_not_a_disagreement():
    an = A.analyse("Empty miles came down 18% for my board.",
                   prior_claims=_claims(DISPATCH_RESUME))
    assert an.contradicts == []


def test_the_contradiction_quotes_the_resume_rather_than_the_extractor():
    """"your resume says 18% for reduced" is not a sentence anyone says."""
    an = A.analyse("I had 3 drivers reporting to me directly.",
                   prior_claims=_claims(DISPATCH_RESUME))
    assert '"Managed 12 drivers day to day"' in an.contradicts[0]


def test_the_contradiction_probe_is_not_an_accusation():
    an = A.analyse("I had 3 drivers reporting to me directly.",
                   prior_claims=_claims(DISPATCH_RESUME))
    probe = F.decide(an, probe_depth=0, max_probe_depth=3, evidence_count=0,
                     min_evidence=1, competency_key="driver_relationships")
    text = probe.followup.question_text.lower()
    assert "rather understand it than guess" in text
    for accusation in ("disagrees", "inconsistent", "wrong", "incorrect"):
        assert accusation not in text


# ===========================================================================
# The recruiter debrief
# ===========================================================================

class _Ev:
    def __init__(self, key, polarity, kind, quote, strength=0.7, start=1000):
        self.competency_key = key
        self.polarity = polarity
        self.evidence_kind = kind
        self.quote = quote
        self.strength = strength
        self.quote_start_ms = start
        self.id = f"ev-{key}-{kind}-{polarity}"


def _scorecard_with(scores: dict):
    from app.interview import scoring as S
    assessments = [
        S.Assessment(competency_key=k, state=S.SCORED, score=v,
                     confidence=0.7, rationale="meets the bar on the evidence "
                                               "gathered. Based on 2 items.",
                     missing_evidence="a specific instance",
                     supporting_ids=[f"s-{k}"], contradicting_ids=[])
        for k, v in scores.items()]
    return S.Scorecard(rubric_key="dispatcher", rubric_version="2026.08.29",
                       assessments=assessments, overall_state="SCORED",
                       completeness_state=S.COMPLETE, uncovered_required=[],
                       overall_score=1.9, overall_confidence=0.7)


def _debrief(scores: dict):
    from app.interview import summary as SU
    ev = {k: [_Ev(k, "SUPPORTS", "SPECIFIC_EXAMPLE", f"quote for {k}")]
          for k in scores}
    return SU.build_debrief(scorecard=_scorecard_with(scores),
                            evidence_by_competency=ev)


def test_no_competency_appears_as_both_a_strength_and_a_weakness():
    """Strengths took the top four by score whatever those scores were, and
    weaknesses took everything under 2.0. "Ownership — 1.65/4" appeared in
    BOTH lists, with the same number, on the same screen."""
    d = _debrief({"exception_handling": 3.17, "load_planning": 2.39,
                  "driver_relationships": 2.29, "ownership": 1.65,
                  "problem_solving": 1.51, "evidence_specificity": 1.59,
                  "communication": 0.71})
    strong = {i.competency_key for i in d.strengths}
    thin = {i.competency_key for i in d.weaknesses}
    assert not (strong & thin), sorted(strong & thin)


def test_every_weakness_can_be_played_back():
    """The user-facing requirement: clicking any assessment seeks the actual
    recording. Weaknesses looked only at CONTRADICTS evidence, so a
    low-scoring competency with only weak supporting evidence rendered with no
    ids, no quote and no timecode -- the half of the debrief that changes a
    decision was the half a recruiter could not play."""
    d = _debrief({"ownership": 1.65, "communication": 0.71,
                  "exception_handling": 3.1})
    assert d.weaknesses
    for item in d.weaknesses:
        assert item.evidence_ids, item.text
        assert item.quote, item.text
        assert item.start_ms is not None, item.text


def test_every_strength_can_be_played_back():
    d = _debrief({"ownership": 1.65, "exception_handling": 3.1})
    assert d.strengths
    for item in d.strengths:
        assert item.evidence_ids and item.quote and item.start_ms is not None


def test_a_weakness_does_not_claim_to_meet_the_bar():
    """`rationale` carries the score BAND, which rounds: 1.65 read "meets the
    bar on the evidence gathered", printed under the heading "weaknesses"."""
    d = _debrief({"ownership": 1.65, "exception_handling": 3.1})
    for item in d.weaknesses:
        assert "meets the bar" not in item.text
        assert "Still needed" in item.text


def test_weaknesses_are_ordered_worst_first():
    d = _debrief({"ownership": 1.65, "communication": 0.71,
                  "problem_solving": 1.51, "exception_handling": 3.1})
    keys = [i.competency_key for i in d.weaknesses]
    assert keys[0] == "communication"


def test_the_debrief_stays_short_enough_to_read():
    """"Readable in two minutes" is the product claim. Four items a side is
    the budget; an unbounded list is a wall of text with a headline on top."""
    d = _debrief({f"c{i}": 0.5 + i * 0.1 for i in range(12)})
    assert len(d.strengths) <= 4 and len(d.weaknesses) <= 4


# ===========================================================================
# The second contradiction detector
# ===========================================================================

def _claim(value, unit, subject, ctype="MEASURABLE_OUTCOME"):
    return type("C", (), {"quantity_value": value, "quantity_unit": unit,
                          "claim_type": ctype, "subject": subject,
                          "id": None})()


_SUPPORT = [type("E", (), {"polarity": "SUPPORTS", "id": None,
                           "evidence_kind": "SPECIFIC_EXAMPLE"})()]


def test_verification_does_not_contradict_across_units():
    """`analysis._detect_contradictions` had this defect and was fixed; this
    detector kept it, and it is the more damaging of the two -- its output is
    a CONTRADICTED verdict written onto the recruiter's debrief rather than a
    question asked in the room."""
    from app.interview import verification as V
    v = V.verify_claim(_claim(18.0, "%", "empty miles"),
                       ["Empty miles improved once we ran 40 trucks."],
                       evidence=_SUPPORT)
    assert v.verdict != V.CONTRADICTED
    assert v.verdict == V.INSUFFICIENT_EVIDENCE


def test_verification_still_contradicts_within_a_unit():
    """Positive control."""
    from app.interview import verification as V
    v = V.verify_claim(_claim(18.0, "%", "empty miles"),
                       ["We cut empty miles by 35% that year."],
                       evidence=_SUPPORT)
    assert v.verdict == V.CONTRADICTED
    assert "18%" in v.rationale and "35%" in v.rationale


def test_a_dollar_claim_is_compared_in_dollars():
    """The unit key is stored "USD" and this caller lowercased it, so every
    dollar claim fell through to the counted-noun path and matched nothing."""
    from app.interview import verification as V
    v = V.verify_claim(_claim(50_000.0, "USD", "freight spend"),
                       ["I cut freight spend by $120,000."],
                       evidence=_SUPPORT)
    assert v.verdict == V.CONTRADICTED
    assert "$50,000" in v.rationale and "$120,000" in v.rationale


def test_a_restated_figure_is_not_a_contradiction():
    from app.interview import verification as V
    v = V.verify_claim(_claim(18.0, "%", "empty miles"),
                       ["Empty miles came down 18% on my board."],
                       evidence=_SUPPORT)
    assert v.verdict in (V.SUPPORTED, V.PARTIALLY_SUPPORTED)


def test_the_recruiter_debrief_uses_the_roles_vocabulary():
    """"still needed: what the candidate personally decided, BUILT or handled"
    reached a recruiter hiring a dispatcher."""
    for r in (RB.CDL_DRIVER, RB.DISPATCHER, RB.FREIGHT_BROKER):
        assert "built" not in r.get("ownership").evidence_needed, r.key
    assert "built" in RB.SOFTWARE_ENGINEER.get("ownership").evidence_needed


# ===========================================================================
# Scoring: what "still needed" says, and what a met requirement is worth
# ===========================================================================

class _E:
    def __init__(self, kind, strength=0.8, polarity="SUPPORTS"):
        self.evidence_kind = kind
        self.strength = strength
        self.polarity = polarity
        self.id = f"{kind}-{strength}"


SAFETY_NEEDED = ("a specific situation where the candidate chose to stop, "
                 "refuse, or delay, and what happened as a result")


def S_expected(needed):
    from app.interview import scoring as S
    return S.expected_kinds(needed)


def _assess(kinds, needed=SAFETY_NEEDED, negatives=()):
    from app.interview import scoring as S
    ev = [_E(k) for k in kinds] + [_E(k, 0.5, "CONTRADICTS") for k in negatives]
    return S.assess_competency("safety_judgement", ev, evidence_needed=needed)


def test_still_needed_does_not_name_what_the_candidate_provided():
    """A recruiter read

        Safety judgement — 1.6/4.
        Still needed: a specific situation where the candidate chose to stop…
        ▸ "Coming through Amarillo in February the road was glazing over…"

    -- the thing said to be missing, quoted underneath it."""
    a = _assess(["SPECIFIC_EXAMPLE"])
    assert a.missing_evidence is not None
    assert "chose to stop, refuse, or delay" not in (a.missing_evidence or "")
    assert "personally" in a.missing_evidence, (
        "OWNERSHIP is the kind that is absent; that is what should be named")


def test_still_needed_names_the_absent_kind():
    a = _assess(["OWNERSHIP", "OWNERSHIP"])
    assert "one specific instance" in a.missing_evidence


def test_nothing_is_reported_missing_when_nothing_is(monkeypatch):
    a = _assess(["SPECIFIC_EXAMPLE", "OWNERSHIP", "TRADEOFF_REASONING"])
    assert a.missing_evidence is None or "second example" in a.missing_evidence


def test_a_metric_competency_still_asks_for_a_number():
    """The conditional expectations are what stop this from becoming a rule
    that everything is fine."""
    a = _assess(["SPECIFIC_EXAMPLE", "OWNERSHIP"],
                needed="a metric the candidate personally moved, with the "
                       "baseline and the mechanism")
    assert a.missing_evidence and "number" in a.missing_evidence


#: exception_handling's real wording. It asks for an instance and for what the
#: candidate did -- and, deliberately, for nothing that implies a weighed
#: alternative, so this is the case where the requirement CAN be fully met by
#: one complete answer.
BREAKDOWN_NEEDED = ("a specific breakdown, late appointment, detention or "
                    "refused load, including who the candidate contacted and "
                    "how it was documented")


def test_a_fully_met_requirement_is_not_materially_incomplete():
    """A driver's account of a reefer failure -- the equipment, the freight,
    the temperature log, the two calls, the shop inside ninety minutes -- is
    exactly what exception_handling asks for, in full, and scored 1.6/4:
    "some signal, materially incomplete."

    The curve rewards breadth, and breadth is partly a property of the ENGINE:
    `followup.decide` stops probing once an answer leaves no material gap, so
    answering completely the first time produces fewer rows.
    """
    a = _assess(["SPECIFIC_EXAMPLE", "OWNERSHIP"], needed=BREAKDOWN_NEEDED)
    assert a.score >= 2.0
    assert "every kind of evidence this competency asks for is present" in \
        a.rationale


def test_a_requirement_that_asks_for_a_weighed_decision_is_not_floored():
    """safety_judgement asks for a situation the candidate CHOSE to stop in,
    so a tradeoff is part of its requirement and two kinds do not meet it.
    This is what stops the floor from becoming "everything scores 2"."""
    a = _assess(["SPECIFIC_EXAMPLE", "OWNERSHIP"])
    assert a.score < 2.0
    assert "TRADEOFF_REASONING" in S_expected(SAFETY_NEEDED)


def test_the_floor_does_not_apply_when_something_contradicts():
    """A met requirement with a contradiction in it is precisely the case a
    human needs to look at, so it must not be rounded up to the bar."""
    a = _assess(["SPECIFIC_EXAMPLE", "OWNERSHIP"], needed=BREAKDOWN_NEEDED,
                negatives=["CONTRADICTION"])
    assert a.score < 2.0


def test_the_floor_does_not_apply_to_a_half_met_requirement():
    """Positive control the other way: a floor that applied regardless would
    make every probed competency score 2."""
    a = _assess(["SPECIFIC_EXAMPLE"])
    assert a.score < 2.0


def test_the_floor_is_a_floor_and_not_a_cap():
    a = _assess(["SPECIFIC_EXAMPLE", "OWNERSHIP", "QUANTIFIED_OUTCOME",
                 "TRADEOFF_REASONING", "FAILURE_REFLECTION"],
                needed=BREAKDOWN_NEEDED)
    assert a.score > 2.0


def test_a_tradeoff_stated_in_a_drivers_words_is_recognised():
    """The second vocabulary defect of the same shape as the ownership one:
    "we lost the appointment and the receiver charged us a redelivery. I would
    do it again" is a cost paid on purpose, and matched none of the
    business-school phrases the detector was built from."""
    an = A.analyse(
        "I shut down at a truck stop and called dispatch before they called "
        "me. We lost the appointment and the receiver charged us a "
        "redelivery. I would do it again.")
    assert an.has_tradeoff


@pytest.mark.parametrize("answer", [
    "We lost the appointment because the receiver would not take us.",
    "I decided to run it overnight.",
    "The load was late and the customer was unhappy.",
])
def test_a_bad_outcome_alone_is_not_a_tradeoff(answer):
    """Negative control. A cost with no sign it was chosen is a bad outcome,
    and a choice with no cost is just a decision."""
    assert not A.analyse(answer).has_tradeoff


def test_every_scored_competency_reaches_the_debrief():
    """Strengths take the top four and weaknesses take everything below the
    bar, so a competency at the bar and fifth-best appeared in neither."""
    d = _debrief({"a": 3.2, "b": 3.1, "c": 3.0, "d": 2.9, "e": 2.5, "f": 2.1})
    seen = ({i.competency_key for i in d.strengths}
            | {i.competency_key for i in d.weaknesses}
            | {i.competency_key for i in d.also_assessed})
    assert seen == {"a", "b", "c", "d", "e", "f"}


# ===========================================================================
# The interview row describes itself
# ===========================================================================

def test_finalising_records_when_the_interview_ended():
    """An interview marked COMPLETED with no end time is a row that
    contradicts itself. The column existed and nothing wrote it, so every
    list showed "finished: —" beside a COMPLETED badge and no report could say
    how long an interview took.

    Read as source: the write is one line inside an async database path, and
    the property being asserted is that the line is there at all.
    """
    src = (pathlib.Path(__file__).parent.parent / "app" / "interview"
           / "runner.py").read_text()
    finalise = src[src.index('interview.status = "COMPLETED"'):]
    assert "interview.ended_at" in finalise[:600], (
        "finalise marks the interview COMPLETED without recording when")
    assert "if interview.ended_at is None" in finalise[:600], (
        "a re-finalise must not move the original end time")


def test_starting_records_when_the_interview_began():
    src = (pathlib.Path(__file__).parent.parent / "app" / "interview"
           / "runner.py").read_text()
    assert "if interview.started_at is None" in src, (
        "starting an attempt must set the interview's own start time")


# ===========================================================================
# One question at a time
# ===========================================================================

def _returned_question_strings(module_path):
    """Every string a `return` in this module can produce, via the AST.

    AST rather than a regex, because the first version of this test used one
    and it did not work: the question literals contain escaped quotes, the
    character class stopped at the first one, and the pattern matched NOTHING.
    It passed against a deliberately re-compounded question -- a detector that
    cannot detect, which is worse than no test, because the green tick is read
    as evidence.
    """
    import ast

    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    out = []

    def literal_of(node):
        """Concatenated literal text of a string/f-string expression."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(literal_of(v) for v in node.values)
        if isinstance(node, ast.FormattedValue):
            return " "                      # a placeholder is not punctuation
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return literal_of(node.left) + literal_of(node.right)
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            text = literal_of(node.value)
            if text.strip():
                out.append(" ".join(text.split()))
    return out


def test_no_generated_question_asks_three_things_at_once():
    """A person asked three things answers one, and the other two are quietly
    dropped -- so the interview looks rigorous and gathers less.

    The metric opener used to do exactly that: what produced the problem
    before, which part of the fix was yours, AND how you established the
    improvement was caused by your change. All three in one breath, and all
    three already covered by followup.py's baseline, ownership and attribution
    probes -- which fire only when an answer has NOT covered them, which is
    the difference between depth that is earned and depth that is recited.
    """
    import pathlib

    planner = pathlib.Path(__file__).parent.parent / "app" / "interview" / "planner.py"
    returned = _returned_question_strings(planner)

    offenders = [t for t in returned if t.count("?") > 1]
    assert not offenders, (
        "generated questions asking more than one thing at once:\n  "
        + "\n  ".join(f"({t.count('?')}) {t[:150]}" for t in offenders))


def test_control_the_question_scanner_actually_reads_questions():
    """The scanner passing means nothing if it found no questions to read."""
    import pathlib

    planner = pathlib.Path(__file__).parent.parent / "app" / "interview" / "planner.py"
    returned = _returned_question_strings(planner)
    with_q = [t for t in returned if "?" in t]
    assert len(with_q) >= 5, (
        f"the scanner found only {len(with_q)} question strings in planner.py; "
        f"it is not reading what it claims to read")


def test_the_followup_engine_still_carries_all_three_probes():
    """Splitting the opener is only safe because these exist. If one is
    removed, that line of enquiry disappears from the interview entirely
    rather than moving back into the first question."""
    import pathlib

    src = (pathlib.Path(__file__).parent.parent / "app" / "interview"
           / "followup.py").read_text(encoding="utf-8")
    assert "What was it before?" in src, "the baseline probe is gone"
    assert "_ownership_probe" in src, "the ownership probe is gone"
    assert "How did you know it was your change" in src, (
        "the attribution probe is gone")
