"""Turn an answer into evidence: quotes that support or contradict something.

WHY EVIDENCE IS A ROW AND NOT A NUMBER
The alternative -- and what the previous implementation did -- is to hand a
transcript to a model and keep the score it returns. That produces a number
nobody can check, attached to nothing, which is exactly the thing a recruiter
cannot defend if a candidate or a regulator asks how it was reached.

An evidence row is a QUOTE plus what that quote does. It carries the answer it
came from, the question that provoked it, the claim it relates to, the
competency it bears on, and -- once transcription has run -- the transcript
segment and the millisecond offsets. That last part is what lets the recruiter
UI turn a score into a click that starts the video at the moment the candidate
said it.

EXTRACTION IS CONSERVATIVE
A sentence becomes evidence only when it does something identifiable: names a
specific instance, states personal action, carries a supported number, weighs
an alternative, admits a limit, or contradicts a prior claim. Sentences that
merely sound good produce nothing. An answer that yields no evidence is a real
outcome and leads to INSUFFICIENT_EVIDENCE downstream, which is the honest
result rather than a low score invented to fill the column.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from app.interview import claims as C
from app.interview.analysis import (AnswerAnalysis, _ALTERNATIVE, _ATTRIBUTION,
                                    _BASELINE, _CONFLICT, _FAILURE,
                                    _FIRST_PERSON_ACTIVE, _NUMBER, _PROPER,
                                    _COST_INCURRED, _TIMEFRAME,
                                    _TRADEOFF_EXPLICIT)

EVIDENCE_VERSION = "evidence-2026.08.29"

SUPPORTS = "SUPPORTS"
CONTRADICTS = "CONTRADICTS"
NEUTRAL = "NEUTRAL"

SPECIFIC_EXAMPLE = "SPECIFIC_EXAMPLE"
OWNERSHIP = "OWNERSHIP"
QUANTIFIED_OUTCOME = "QUANTIFIED_OUTCOME"
TRADEOFF_REASONING = "TRADEOFF_REASONING"
FAILURE_REFLECTION = "FAILURE_REFLECTION"
CONFLICT_HANDLING = "CONFLICT_HANDLING"
DOMAIN_DEPTH = "DOMAIN_DEPTH"
VAGUENESS = "VAGUENESS"
UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
CONTRADICTION = "CONTRADICTION"
NON_ANSWER = "NON_ANSWER"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ExtractedEvidence:
    competency_key: str
    polarity: str
    evidence_kind: str
    quote: str
    rationale: str
    strength: float
    claim_id: object = None
    quote_start_ms: Optional[int] = None
    quote_end_ms: Optional[int] = None

    def as_row(self, *, answer_id, question_id=None, competency_id=None,
               transcript_segment_id=None) -> dict:
        return {
            "competency_key": self.competency_key,
            "competency_id": competency_id,
            "claim_id": self.claim_id,
            "question_id": question_id,
            "answer_id": answer_id,
            "transcript_segment_id": transcript_segment_id,
            "polarity": self.polarity,
            "evidence_kind": self.evidence_kind,
            "quote": self.quote,
            "quote_start_ms": self.quote_start_ms,
            "quote_end_ms": self.quote_end_ms,
            "strength": self.strength,
            "rationale": self.rationale,
            "extracted_by": EVIDENCE_VERSION,
        }


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s.strip()]


def _best(sentences: Sequence[str], pattern) -> Optional[str]:
    """The first sentence matching a pattern -- the quote a recruiter reads."""
    for s in sentences:
        if pattern.search(s):
            return s
    return None


def extract(answer_text: str, analysis: AnswerAnalysis, *,
            competency_key: str,
            hook_claim: Optional[C.Claim] = None,
            answer_start_ms: Optional[int] = None,
            answer_end_ms: Optional[int] = None) -> List[ExtractedEvidence]:
    """Evidence for ONE competency from ONE answer.

    Timecodes are the answer's own span. Sub-sentence offsets would need
    word-level alignment from the transcriber; claiming precision we do not
    have would make a recruiter's click land in the wrong place, which is worse
    than landing at the start of the answer.
    """
    out: List[ExtractedEvidence] = []
    claim_id = getattr(hook_claim, "_row_id", None)

    def add(polarity: str, kind: str, quote: str, rationale: str,
            strength: float) -> None:
        q = " ".join((quote or "").split())
        if not q:
            return
        out.append(ExtractedEvidence(
            competency_key=competency_key, polarity=polarity,
            evidence_kind=kind, quote=q[:1200], rationale=rationale,
            strength=round(max(0.0, min(1.0, strength)), 3),
            claim_id=claim_id,
            quote_start_ms=answer_start_ms, quote_end_ms=answer_end_ms))

    if not analysis.is_substantive:
        add(NEUTRAL, NON_ANSWER, answer_text or "(no answer)",
            f"the candidate did not answer ({analysis.non_answer_kind}); this "
            f"is recorded so the competency shows as unprobed rather than weak",
            0.0)
        return out

    sentences = _sentences(answer_text)

    # --- contradiction first: it changes how everything else reads ---------
    for detail in analysis.contradicts:
        add(CONTRADICTS, CONTRADICTION,
            _best(sentences, _NUMBER) or answer_text,
            f"the answer appears to disagree with a resume claim — {detail}. "
            f"Recorded as something to resolve, not as dishonesty.",
            0.6)

    # --- ownership ---------------------------------------------------------
    if analysis.has_first_person_action:
        quote = _best(sentences, _FIRST_PERSON_ACTIVE)
        add(SUPPORTS, OWNERSHIP, quote or answer_text,
            "the candidate names a specific action they took themselves, "
            "rather than describing a team outcome",
            0.75 if analysis.is_specific else 0.55)
    elif analysis.team_voice_only:
        add(CONTRADICTS, VAGUENESS,
            _best(sentences, re.compile(r"\bwe\b", re.I)) or answer_text,
            "the answer describes the team's work without identifying what "
            "the candidate personally did; the follow-up asked for this",
            0.4)

    # --- specificity -------------------------------------------------------
    if analysis.is_specific:
        add(SUPPORTS, SPECIFIC_EXAMPLE,
            _best(sentences, _PROPER) or sentences[0],
            f"names {analysis.named_specifics} specific system, tool or party "
            f"and describes a particular instance",
            min(0.9, 0.5 + 0.1 * analysis.named_specifics))
    elif analysis.is_generic_approach:
        add(CONTRADICTS, VAGUENESS, sentences[0],
            "describes a general approach rather than a particular instance, "
            "after being asked for a specific example",
            0.45)

    # --- quantitative ------------------------------------------------------
    # Only an OUTCOME number is judged as a measurement. A descriptive
    # quantity is part of a specific example, not an unsupported metric.
    if analysis.has_outcome_number:
        quote = _best(sentences, _NUMBER) or answer_text
        if analysis.quantitative_claim_is_supported:
            supports = [n for n, ok in (("a baseline", analysis.has_baseline),
                                        ("a time period", analysis.has_timeframe),
                                        ("an attribution", analysis.has_attribution))
                        if ok]
            add(SUPPORTS, QUANTIFIED_OUTCOME, quote,
                f"states a measured result with {', '.join(supports)}",
                0.85)
        else:
            missing = [n for n, ok in (("a baseline", analysis.has_baseline),
                                       ("a time period", analysis.has_timeframe),
                                       ("an attribution", analysis.has_attribution))
                       if not ok]
            add(CONTRADICTS, UNSUPPORTED_METRIC, quote,
                f"states a number without {', '.join(missing)}; the figure is "
                f"not yet a measurement",
                0.5)

    # --- reasoning ---------------------------------------------------------
    if analysis.has_alternative or analysis.has_tradeoff:
        # The quote for a tradeoff is the sentence naming the cost when there
        # is no explicit "trade-off" phrasing, because that is the sentence a
        # recruiter should be sent to.
        quote = (_best(sentences, _TRADEOFF_EXPLICIT)
                 or _best(sentences, _ALTERNATIVE)
                 or _best(sentences, _COST_INCURRED)
                 or answer_text)
        add(SUPPORTS, TRADEOFF_REASONING, quote,
            "weighs an alternative or names what was given up, rather than "
            "presenting the choice as obvious",
            0.8)

    if analysis.has_failure_reflection:
        add(SUPPORTS, FAILURE_REFLECTION, _best(sentences, _FAILURE) or answer_text,
            "identifies a limit, mistake or thing they would change — evidence "
            "the candidate understands the boundaries of their own work",
            0.7)

    if analysis.has_conflict_account:
        add(SUPPORTS, CONFLICT_HANDLING, _best(sentences, _CONFLICT) or answer_text,
            "describes a real disagreement and what they did about it",
            0.75)

    return out
