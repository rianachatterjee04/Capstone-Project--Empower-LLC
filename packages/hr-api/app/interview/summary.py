"""The recruiter debrief: structured, evidence-linked, readable in two minutes.

WHY NOT A PARAGRAPH
An LLM paragraph about a candidate is unfalsifiable. It reads well, it cannot
be checked, and a recruiter who disagrees with it has nothing to disagree
WITH. Worse, it launders the difference between "the candidate demonstrated
this" and "the model inferred this".

So every line of this debrief is a structured item carrying the evidence ids
behind it. The recruiter UI turns each one into a click that starts the
recording at the moment the candidate said it. A strength with no evidence id
cannot be rendered, which is the intended constraint.

WHAT THE DEBRIEF MUST SAY OUT LOUD
What the interview did NOT establish. That is the section most tools omit, and
it is the one that changes a hiring decision: a recruiter who knows safety
judgement was never probed will ask about it in the next round, while one who
sees a tidy scorecard assumes it was covered.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from app.interview import scoring as S

SUMMARY_VERSION = "summary-2026.08.29"


@dataclass
class SummaryItem:
    text: str
    competency_key: Optional[str] = None
    evidence_ids: List[object] = field(default_factory=list)
    quote: Optional[str] = None
    start_ms: Optional[int] = None

    def as_dict(self) -> dict:
        return {"text": self.text, "competency_key": self.competency_key,
                "evidence_ids": [str(e) for e in self.evidence_ids if e],
                "quote": self.quote, "start_ms": self.start_ms}


@dataclass
class Debrief:
    headline: str
    overall_assessment: str
    strengths: List[SummaryItem] = field(default_factory=list)
    weaknesses: List[SummaryItem] = field(default_factory=list)
    #: Scored, at the bar, and not among the strongest four. One line, because
    #: a two-minute debrief cannot list everything at length -- but dropping
    #: them entirely would let a competency be assessed and then silently
    #: disappear from the summary of the assessment.
    also_assessed: List[SummaryItem] = field(default_factory=list)
    contradictions: List[SummaryItem] = field(default_factory=list)
    unresolved_questions: List[SummaryItem] = field(default_factory=list)
    recommended_followup: List[SummaryItem] = field(default_factory=list)
    generated_by: str = SUMMARY_VERSION

    def as_rows(self) -> dict:
        return {
            "headline": self.headline,
            "overall_assessment": self.overall_assessment,
            "strengths": [i.as_dict() for i in self.strengths],
            "weaknesses": [i.as_dict() for i in self.weaknesses],
            "also_assessed": [i.as_dict() for i in self.also_assessed],
            "contradictions": [i.as_dict() for i in self.contradictions],
            "unresolved_questions": [i.as_dict() for i in self.unresolved_questions],
            "recommended_followup": [i.as_dict() for i in self.recommended_followup],
            "generated_by": self.generated_by,
        }


def _label(assessments: Sequence[S.Assessment]) -> Dict[str, S.Assessment]:
    return {a.competency_key: a for a in assessments}


def build_debrief(*, scorecard: S.Scorecard,
                  evidence_by_competency: Dict[str, list],
                  competency_labels: Optional[Dict[str, str]] = None,
                  verifications: Sequence = (),
                  candidate_name: str = "The candidate") -> Debrief:
    """Assemble the debrief from the scorecard and the evidence behind it."""
    labels = competency_labels or {}

    def label(key: str) -> str:
        return labels.get(key, key.replace("_", " "))

    scored = [a for a in scorecard.assessments if a.state == S.SCORED]
    unscored = [a for a in scorecard.assessments if a.state != S.SCORED]

    # --- headline ---------------------------------------------------------
    if not scored:
        headline = ("The interview did not establish enough to assess this "
                    "candidate on any competency.")
    else:
        best = max(scored, key=lambda a: a.score or 0)
        headline = (
            f"Strongest on {label(best.competency_key)} "
            f"({best.score}/4). "
            f"{len(scored)} of {len(scorecard.assessments)} competencies were "
            f"established from what the candidate said.")

    completeness = (
        "Every required competency was covered."
        if scorecard.completeness_state == S.COMPLETE else
        f"NOT COVERED: {', '.join(label(k) for k in scorecard.uncovered_required)}. "
        f"The overall figure is calculated only over what was established, so "
        f"it is not comparable with a complete interview.")

    overall = (
        f"Overall {scorecard.overall_score}/4 "
        f"(confidence {scorecard.overall_confidence}). {completeness} "
        f"This is decision support for a human recruiter, not a hiring "
        f"recommendation.")

    d = Debrief(headline=headline, overall_assessment=overall)

    # --- strengths and weaknesses, on one boundary ------------------------
    #
    # THESE USED TO OVERLAP.
    # Strengths took the top four by score whatever those scores were, and
    # weaknesses took everything under 2.0. In a seven-competency interview
    # where four scored below 2.0, "Ownership — 1.65/4" appeared in BOTH
    # lists, with the same number, on the same screen. A recruiter reading
    # that stops trusting the whole page, and they are right to.
    #
    # One boundary, applied once. A competency is on exactly one side of it.
    STRONG_ENOUGH = 2.0
    strong = sorted([a for a in scored if (a.score or 0) >= STRONG_ENOUGH],
                    key=lambda x: -(x.score or 0))
    thin = sorted([a for a in scored if (a.score or 0) < STRONG_ENOUGH],
                  key=lambda x: (x.score or 0))

    def _playable(key: str, prefer: str):
        """The evidence a recruiter should be sent to, and where it starts.

        Prefers `prefer` polarity, then falls back to anything. A weakness
        with no clickable evidence is the failure this exists to prevent: the
        half of the debrief that changes a decision was the half a recruiter
        could not play.
        """
        evs = list(evidence_by_competency.get(key, []))
        if not evs:
            return [], None, None
        preferred = [e for e in evs if getattr(e, "polarity", "") == prefer]
        pool = preferred or evs
        best = max(pool, key=lambda e: float(getattr(e, "strength", 0) or 0))
        return ([getattr(e, "id", None) for e in pool],
                getattr(best, "quote", None),
                getattr(best, "quote_start_ms", None))

    for a in strong[:4]:
        ids, quote, start = _playable(a.competency_key, "SUPPORTS")
        if not ids:
            continue
        d.strengths.append(SummaryItem(
            text=f"{label(a.competency_key)} — {a.score}/4. {a.rationale}",
            competency_key=a.competency_key,
            evidence_ids=ids, quote=quote, start_ms=start))

    # EVERY SCORED COMPETENCY IS ACCOUNTED FOR.
    # Strengths take the top four and weaknesses take everything under the
    # bar, so a competency that is at the bar and fifth-best appeared in
    # neither -- assessed, then absent from the assessment.
    for a in strong[4:]:
        ids, quote, start = _playable(a.competency_key, "SUPPORTS")
        d.also_assessed.append(SummaryItem(
            text=f"{label(a.competency_key)} — {a.score}/4",
            competency_key=a.competency_key,
            evidence_ids=ids, quote=quote, start_ms=start))

    for a in thin[:4]:
        # DO NOT REUSE THE SCORE BAND HERE.
        # `rationale` carries the band for the ROUNDED score, so 1.65 read
        # "meets the bar on the evidence gathered" -- printed underneath the
        # heading "weaknesses". The item now says what is actually thin.
        ids, quote, start = _playable(a.competency_key, "CONTRADICTS")
        detail = (f"{a.supporting_count} supporting item(s)"
                  if a.supporting_count else "nothing that supports it")
        if a.contradicting_count:
            detail += f", {a.contradicting_count} against"
        # "Still needed: more of what the rubric asks for" was the fallback
        # here, which is a sentence that means nothing. When `scoring` can
        # name no absent kind, the honest thing to say is that nothing is
        # absent -- so the recruiter reads the number as brevity rather than
        # as a red flag.
        tail = (f"Still needed: {a.missing_evidence}" if a.missing_evidence
                else ("Every kind of evidence this competency asks for is "
                      "present; the score reflects how much was said, not "
                      "what was missing."))
        d.weaknesses.append(SummaryItem(
            text=(f"{label(a.competency_key)} — {a.score}/4, on {detail}. "
                  f"{tail}"),
            competency_key=a.competency_key,
            evidence_ids=ids, quote=quote, start_ms=start))

    for a in unscored:
        # An absence is NOT a weakness and is listed separately, because a
        # recruiter skimming a "weaknesses" list will read it as one.
        d.unresolved_questions.append(SummaryItem(
            text=(f"{label(a.competency_key)} — {a.state}. "
                  f"{a.missing_evidence or a.rationale}"),
            competency_key=a.competency_key))

    # --- contradictions ---------------------------------------------------
    for key, evs in evidence_by_competency.items():
        for e in evs:
            if getattr(e, "evidence_kind", "") != "CONTRADICTION":
                continue
            d.contradictions.append(SummaryItem(
                text=getattr(e, "rationale", "an apparent disagreement"),
                competency_key=key,
                evidence_ids=[getattr(e, "id", None)],
                quote=getattr(e, "quote", None),
                start_ms=getattr(e, "quote_start_ms", None)))

    for v in verifications:
        verdict = getattr(v, "verdict", "")
        if verdict in ("CONTRADICTED", "PARTIALLY_SUPPORTED"):
            d.contradictions.append(SummaryItem(
                text=f"{verdict}: {getattr(v, 'rationale', '')}",
                evidence_ids=list(getattr(v, "evidence_ids", []) or [])))

    # --- what a human should do next --------------------------------------
    for key in scorecard.uncovered_required:
        d.recommended_followup.append(SummaryItem(
            text=(f"Ask about {label(key)} directly — the AI interview did not "
                  f"establish it, so this round says nothing about it."),
            competency_key=key))
    for item in d.contradictions[:2]:
        d.recommended_followup.append(SummaryItem(
            text=("Resolve the point above with the candidate. Incomplete "
                  "evidence is normal; the purpose is to understand it, not to "
                  "challenge them."),
            competency_key=item.competency_key,
            evidence_ids=item.evidence_ids))
    if not d.recommended_followup and scored:
        weakest = min(scored, key=lambda a: a.score or 0)
        d.recommended_followup.append(SummaryItem(
            text=(f"Go deeper on {label(weakest.competency_key)} in a human "
                  f"round — it is the least-evidenced competency here."),
            competency_key=weakest.competency_key))

    return d
