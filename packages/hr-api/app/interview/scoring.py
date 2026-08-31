"""Score competencies from evidence, and admit when there isn't any.

THE RULE
A score is a function of evidence rows. Not of the transcript, not of how the
candidate sounded, not of a model's overall impression. If the evidence for a
competency is thin, the result is INSUFFICIENT_EVIDENCE -- a real state with
its own column constraint, not a low score.

WHY THAT MATTERS MORE THAN IT SOUNDS
A rubric that must emit a number will emit one. A candidate who was never
asked about safety judgement, or who was asked and gave a non-answer, would
otherwise receive a middling score that looks like a finding. Two candidates
then get compared on a dimension where one has evidence and the other has a
placeholder, and the placeholder wins or loses on nothing at all.

`competency_assessments_score_ck` enforces this at the database: a row in
state INSUFFICIENT_EVIDENCE cannot carry a score, so no downstream code can
quietly fill it in.

WHAT IS NOT AN INPUT
Appearance, video, audio characteristics, accent, pace, name, age, school,
address, photograph. None of these reaches this module, because none of them
produces an evidence row -- `evidence.py` only emits quotes. The fairness
tests re-run scoring with the name changed and with the video swapped and
assert the numbers are identical, which they must be: neither is reachable
from here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

SCORING_VERSION = "scoring-2026.08.29"

SCORED = "SCORED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
NOT_PROBED = "NOT_PROBED"

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"

#: 0..4, matching the column constraint. Deliberately coarse: a rubric that
#: distinguishes 2.7 from 2.9 from a twenty-minute conversation is claiming a
#: precision the evidence cannot carry.
SCALE = {
    0: "no evidence of the competency",
    1: "some signal, materially incomplete",
    2: "meets the bar on the evidence gathered",
    3: "clearly demonstrated with specifics",
    4: "demonstrated with depth, measurement and reflection",
}

#: Evidence kinds that carry real weight toward a positive score, and how much.
_POSITIVE_WEIGHT = {
    "QUANTIFIED_OUTCOME": 1.0,
    "TRADEOFF_REASONING": 0.9,
    "OWNERSHIP": 0.85,
    "SPECIFIC_EXAMPLE": 0.8,
    "CONFLICT_HANDLING": 0.8,
    "FAILURE_REFLECTION": 0.7,
    "DOMAIN_DEPTH": 0.8,
}

_NEGATIVE_WEIGHT = {
    "CONTRADICTION": 1.0,
    "UNSUPPORTED_METRIC": 0.7,
    "VAGUENESS": 0.6,
}


# WHAT "STILL NEEDED" SHOULD SAY.
# `missing_evidence` used to be the competency's ENTIRE requirement, printed
# whenever the score was under 3. So a recruiter read
#
#   Safety judgement — 1.6/4.
#   Still needed: a specific situation where the candidate chose to stop,
#                 refuse, or delay, and what happened as a result
#   ▸ "Coming through Amarillo in February the road was glazing over…"
#
# The thing it said was still needed, quoted underneath. Nothing makes an
# assessment look less like it read the answer.
#
# It is now derived from the evidence KINDS that are absent, so it names what
# would actually raise the score.
_KIND_GAP = {
    "SPECIFIC_EXAMPLE": ("one specific instance, rather than a description of "
                         "how they generally approach it"),
    "OWNERSHIP": ("what the candidate personally decided or did, distinct "
                  "from what the team did"),
    "QUANTIFIED_OUTCOME": ("a number for the result — or a straight answer "
                           "that none was measured"),
    "TRADEOFF_REASONING": ("an alternative they considered and rejected, and "
                           "what decided it"),
    "FAILURE_REFLECTION": ("a limit, a failure, or something they would do "
                           "differently"),
    "CONFLICT_HANDLING": "a real disagreement and their own part in it",
}

#: Every competency wants these. The rest are added only when the rubric's
#: `evidence_needed` actually asks for them -- demanding a tradeoff from an
#: equipment-experience answer would be the same category error in reverse.
_ALWAYS_EXPECTED = ("SPECIFIC_EXAMPLE", "OWNERSHIP")

_CONDITIONAL_EXPECTED = (
    ("QUANTIFIED_OUTCOME", ("metric", "measur", "number", "rate", "margin")),
    ("TRADEOFF_REASONING", ("alternative", "tradeoff", "trade-off", "decision",
                            "judgement", "judgment", "chose", "rejected")),
    ("FAILURE_REFLECTION", ("limit", "failure", "went wrong", "differently",
                            "mistake")),
    ("CONFLICT_HANDLING", ("disagree", "conflict", "difficult conversation",
                           "pushback")),
)


def expected_kinds(evidence_needed: str) -> List[str]:
    need = (evidence_needed or "").lower()
    kinds = list(_ALWAYS_EXPECTED)
    for kind, triggers in _CONDITIONAL_EXPECTED:
        if any(t in need for t in triggers):
            kinds.append(kind)
    return kinds


def describe_gap(*, present: set, evidence_needed: str,
                 supporting_count: int) -> Optional[str]:
    """What is actually missing, given what was gathered.

    None when nothing identifiable is missing -- at which point saying
    "still needed: <the whole rubric>" would be worse than saying nothing.
    """
    absent = [k for k in expected_kinds(evidence_needed) if k not in present]
    phrases = [_KIND_GAP[k] for k in absent if k in _KIND_GAP]
    if phrases:
        return "; ".join(phrases[:2])
    if supporting_count <= 1:
        return ("a second example — one answer establishes the competency but "
                "does not distinguish a habit from an incident")
    return None


@dataclass
class Assessment:
    competency_key: str
    state: str
    rationale: str
    score: Optional[float] = None
    confidence: Optional[float] = None
    missing_evidence: Optional[str] = None
    supporting_ids: List[object] = field(default_factory=list)
    contradicting_ids: List[object] = field(default_factory=list)

    @property
    def supporting_count(self) -> int:
        return len(self.supporting_ids)

    @property
    def contradicting_count(self) -> int:
        return len(self.contradicting_ids)


@dataclass
class Scorecard:
    rubric_key: str
    rubric_version: str
    assessments: List[Assessment]
    overall_state: str
    completeness_state: str
    uncovered_required: List[str]
    overall_score: Optional[float] = None
    overall_confidence: Optional[float] = None
    decision_authority: str = "RECRUITER_DECISION_SUPPORT"


def assess_competency(competency_key: str, evidence: Sequence,
                      *, min_evidence: int = 1,
                      evidence_needed: str = "") -> Assessment:
    """One competency, from its evidence rows.

    `evidence` items need `.polarity`, `.evidence_kind`, `.strength` and `.id`
    -- satisfied by both the ORM row and the extracted dataclass, so this is
    testable without a database.
    """
    supporting = [e for e in evidence if e.polarity == "SUPPORTS"]
    contradicting = [e for e in evidence if e.polarity == "CONTRADICTS"]
    non_answers = [e for e in evidence
                   if getattr(e, "evidence_kind", None) == "NON_ANSWER"]

    sup_ids = [getattr(e, "id", None) for e in supporting]
    con_ids = [getattr(e, "id", None) for e in contradicting]

    # --- nothing at all ----------------------------------------------------
    if not evidence:
        return Assessment(
            competency_key=competency_key, state=NOT_PROBED,
            rationale=("this competency was never put to the candidate, so "
                       "nothing about it was established either way"),
            missing_evidence=evidence_needed or "any answer on this competency")

    if non_answers and not supporting:
        return Assessment(
            competency_key=competency_key, state=INSUFFICIENT_EVIDENCE,
            rationale=("the candidate was asked and did not answer "
                       "substantively; that is not evidence of weakness, it is "
                       "an absence of evidence"),
            missing_evidence=evidence_needed or "a substantive answer",
            contradicting_ids=con_ids)

    if len(supporting) < min_evidence:
        return Assessment(
            competency_key=competency_key, state=INSUFFICIENT_EVIDENCE,
            rationale=(
                f"{len(supporting)} supporting item(s) against a minimum of "
                f"{min_evidence}. The interview did not establish enough to "
                f"score this either way."),
            missing_evidence=evidence_needed or "more specific evidence",
            confidence=0.25,
            supporting_ids=sup_ids, contradicting_ids=con_ids)

    # --- score from weighted evidence -------------------------------------
    pos = sum(_POSITIVE_WEIGHT.get(e.evidence_kind, 0.5) * float(e.strength)
              for e in supporting)
    neg = sum(_NEGATIVE_WEIGHT.get(e.evidence_kind, 0.5) * float(e.strength)
              for e in contradicting)

    # Distinct kinds matter more than repetition: three specific examples are
    # better than one, but not three times better, and a candidate should not
    # be rewarded for a long answer that repeats itself.
    distinct = len({e.evidence_kind for e in supporting})
    raw = min(4.0, (pos * 0.55) + (distinct * 0.45)) - min(2.0, neg * 0.8)
    score = round(max(0.0, min(4.0, raw)), 2)

    # Confidence is about how much the interview established, not how good the
    # candidate is. More distinct evidence and fewer contradictions raise it.
    confidence = min(0.95, 0.3 + 0.15 * distinct + 0.05 * len(supporting))
    if contradicting:
        confidence = max(0.2, confidence - 0.15 * len(contradicting))

    # A REQUIREMENT THAT IS FULLY MET CANNOT READ AS "MATERIALLY INCOMPLETE".
    #
    # The curve above rewards breadth, and breadth is partly a property of the
    # ENGINE rather than of the candidate: `followup.decide` deliberately stops
    # probing once an answer leaves no material gap, so a candidate who answers
    # completely the first time produces fewer evidence rows than one who has
    # to be asked three more questions. Scoring on row count then punishes them
    # for the interviewer's own decision to move on.
    #
    # What this looked like: a driver's account of a reefer failure -- the
    # equipment, the freight, the temperature log, the two calls, the shop
    # inside ninety minutes -- is exactly what `exception_handling` asks for,
    # in full, and it scored 1.6/4: "some signal, materially incomplete."
    #
    # So a competency whose stated requirement is entirely present is floored
    # at the "meets the bar" band. The headroom above it is for depth --
    # measurement, reflection, a weighed alternative -- which is what the
    # higher bands describe. The floor does NOT apply when anything
    # contradicts, because a met requirement with a contradiction in it is
    # precisely the case a human needs to look at.
    requirement_met = False
    if score < 2.0 and not contradicting:
        wanted = set(expected_kinds(evidence_needed))
        if wanted and wanted <= {e.evidence_kind for e in supporting}:
            requirement_met = True
            score = 2.0

    band = SCALE[int(round(score))] if score <= 4 else SCALE[4]
    bits = [f"{len(supporting)} supporting item(s) across {distinct} kind(s)"]
    if requirement_met:
        bits.append(
            "every kind of evidence this competency asks for is present, so "
            "it is scored at the bar rather than below it")
    if contradicting:
        kinds = sorted({e.evidence_kind for e in contradicting})
        bits.append(f"{len(contradicting)} contradicting ({', '.join(kinds)})")

    return Assessment(
        competency_key=competency_key, state=SCORED, score=score,
        confidence=round(confidence, 3),
        rationale=f"{band}. Based on {'; '.join(bits)}.",
        missing_evidence=(
            None if score >= 3
            else describe_gap(
                present={e.evidence_kind for e in supporting},
                evidence_needed=evidence_needed,
                supporting_count=len(supporting))),
        supporting_ids=sup_ids, contradicting_ids=con_ids)


def build_scorecard(*, rubric_key: str, rubric_version: str,
                    planned: Sequence, evidence_by_competency: Dict[str, list],
                    weights: Optional[Dict[str, float]] = None) -> Scorecard:
    """Assemble the scorecard, including whether the interview was complete.

    `planned` items need `.competency_key`, `.is_required`, `.role_weight`,
    `.min_evidence_count` and `.evidence_needed`.
    """
    assessments: List[Assessment] = []
    uncovered: List[str] = []

    for comp in planned:
        key = comp.competency_key
        a = assess_competency(
            key, evidence_by_competency.get(key, []),
            min_evidence=getattr(comp, "min_evidence_count", 1),
            evidence_needed=getattr(comp, "evidence_needed", ""))
        assessments.append(a)
        if getattr(comp, "is_required", False) and a.state != SCORED:
            uncovered.append(key)

    scored = [a for a in assessments if a.state == SCORED]

    # The weighted mean of what WAS established. Unscored competencies are
    # excluded rather than counted as zero: a competency nobody asked about is
    # not a failure by the candidate.
    overall_score = None
    overall_confidence = None
    if scored:
        w = {}
        for comp in planned:
            w[comp.competency_key] = float(
                (weights or {}).get(comp.competency_key,
                                    getattr(comp, "role_weight", 1.0)))
        total_w = sum(w.get(a.competency_key, 1.0) for a in scored) or 1.0
        overall_score = round(
            sum(float(a.score) * w.get(a.competency_key, 1.0) for a in scored)
            / total_w, 2)
        overall_confidence = round(
            sum(float(a.confidence or 0) for a in scored) / len(scored), 3)

    # An incomplete interview lowers CONFIDENCE in the overall number. It does
    # not lower the score -- the candidate did not cause the gap.
    if uncovered and overall_confidence is not None:
        overall_confidence = round(max(0.15, overall_confidence
                                       - 0.1 * len(uncovered)), 3)

    return Scorecard(
        rubric_key=rubric_key, rubric_version=rubric_version,
        assessments=assessments,
        overall_state=SCORED if scored else INSUFFICIENT_EVIDENCE,
        overall_score=overall_score,
        overall_confidence=overall_confidence,
        completeness_state=COMPLETE if not uncovered else INCOMPLETE,
        uncovered_required=uncovered)
