"""Decide what the interview actually established about each resume claim.

THE CASE THIS EXISTS FOR
A resume says "managed a team of 12". The interview establishes 3 direct
reports and a 12-person cross-functional project group. Both are true. The
candidate did not lie, and a system that reports CONTRADICTED here is making a
character accusation out of an ambiguity in the word "managed".

So the verdict vocabulary has a middle: PARTIALLY_SUPPORTED, carrying what was
actually established, in structured form, alongside the original claim. The
recruiter sees "resume: 12; interview: 3 direct, 12 on the project" and can
decide for themselves whether that is a discrepancy or a normal shorthand.

UNVERIFIED IS NOT A NEGATIVE
A claim nobody asked about is UNVERIFIED. A claim that was asked about and
produced nothing usable is INSUFFICIENT_EVIDENCE. Neither is a mark against
the candidate, and both are distinct from CONTRADICTED, which requires the
answer to actually disagree.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from app.interview.analysis import _amount, _numbers_in_unit

SUPPORTED = "SUPPORTED"
PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
CONTRADICTED = "CONTRADICTED"
UNVERIFIED = "UNVERIFIED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

VERIFICATION_VERSION = "verification-2026.08.29"

#: Words that narrow a leadership claim to direct management.
_DIRECT = re.compile(r"\b(direct(?:ly)?|reported to me|my reports?|"
                     r"line manage\w*)\b", re.IGNORECASE)
#: Words that widen it to influence rather than management.
_INDIRECT = re.compile(r"\b(cross[- ]functional|matrix|project team|"
                       r"working group|dotted line|indirect|virtual team|"
                       r"stakeholders?)\b", re.IGNORECASE)

_NUM = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\b")


@dataclass
class Verification:
    claim_id: object
    verdict: str
    rationale: str
    established_text: Optional[str] = None
    established_value: Optional[float] = None
    established_unit: Optional[str] = None
    confidence: Optional[float] = None
    evidence_ids: List[object] = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "verdict": self.verdict,
            "established_text": self.established_text,
            "established_value": self.established_value,
            "established_unit": self.established_unit,
            "rationale": self.rationale,
            "confidence": self.confidence,
        }


def verify_claim(claim, answers: Sequence[str],
                 evidence: Sequence = ()) -> Verification:
    """One claim against everything the candidate said about it."""
    claim_id = getattr(claim, "id", None)
    text = " ".join(answers or [])
    low = text.lower()
    ev_ids = [getattr(e, "id", None) for e in evidence]

    subject = (getattr(claim, "subject", None) or "").lower()
    words = [w for w in re.findall(r"[a-z]{4,}", subject)]
    discussed = bool(words) and any(w in low for w in words)

    if not text.strip() or not discussed:
        return Verification(
            claim_id=claim_id, verdict=UNVERIFIED,
            rationale=("the interview did not cover this claim, so nothing "
                       "about it was established either way"),
            evidence_ids=ev_ids)

    qty = getattr(claim, "quantity_value", None)

    # --- the "managed 12" case -------------------------------------------
    if qty is not None and getattr(claim, "claim_type", "") == "LEADERSHIP":
        direct = _DIRECT.search(text)
        indirect = _INDIRECT.search(text)
        numbers = [float(n.replace(",", "")) for n in _NUM.findall(text)]
        target = float(qty)
        unit = getattr(claim, "quantity_unit", None) or "people"

        if direct:
            # SCOPE THE NUMBER TO THE SENTENCE THAT SAYS "direct".
            # All the candidate's answers are joined for this check, so a
            # figure from an unrelated answer -- "failures dropped to 0.2%" --
            # would otherwise be read as a headcount. Taking the smallest
            # number across the whole transcript produced exactly that.
            sentences = [s for s in re.split(r"(?<=[.!?])\s+", text)
                         if _DIRECT.search(s)]
            scoped = [float(n.replace(",", ""))
                      for s in sentences for n in _NUM.findall(s)]
            if not scoped:
                return Verification(
                    claim_id=claim_id, verdict=INSUFFICIENT_EVIDENCE,
                    rationale=("the candidate distinguished direct reports "
                               "from a wider group but gave no number for "
                               "either"),
                    confidence=0.3, evidence_ids=ev_ids)
            # Direct reports are a subset of any wider group mentioned in the
            # same breath, so the smaller figure is the direct one.
            established = min(scoped)
            if abs(established - target) <= max(0.1 * target, 0.5):
                return Verification(
                    claim_id=claim_id, verdict=SUPPORTED,
                    established_text=f"{established:g} direct reports",
                    established_value=established, established_unit=unit,
                    rationale=("the candidate described direct management "
                               "matching the claimed number"),
                    confidence=0.8, evidence_ids=ev_ids)
            note = (f"{established:g} direct" +
                    (f", {target:g} on a wider group" if indirect else ""))
            return Verification(
                claim_id=claim_id, verdict=PARTIALLY_SUPPORTED,
                established_text=note,
                established_value=established, established_unit="direct reports",
                rationale=(
                    f"the resume says {target:g} {unit}; the interview "
                    f"establishes {established:g} direct report(s)"
                    + (" alongside a wider cross-functional group. Both can be "
                       "true -- 'managed' covers each. Recorded as a "
                       "distinction, not a discrepancy."
                       if indirect else
                       ". Worth clarifying with the candidate.")),
                confidence=0.7, evidence_ids=ev_ids)

    # --- quantified outcomes ---------------------------------------------
    if qty is not None:
        # THE SECOND UNIT-BLIND COMPARISON.
        # `analysis._detect_contradictions` had the same defect and was fixed;
        # this one survived, and it is the more damaging of the two because
        # its output is a CONTRADICTED verdict written onto the recruiter's
        # debrief rather than a question asked in the room.
        #
        # A dispatcher's "4 years" claim, against an answer containing "40
        # trucks", produced:
        #
        #     CONTRADICTED: the resume claims 4 and the interview produced 40
        #     for the same subject.
        #
        # Four years and forty trucks. Two detectors covering the same ground
        # meant fixing one looked like fixing the problem.
        unit = (getattr(claim, "quantity_unit", None) or "").lower()
        numbers = _numbers_in_unit(text.lower(), unit)
        target = float(qty)
        if not numbers:
            return Verification(
                claim_id=claim_id, verdict=INSUFFICIENT_EVIDENCE,
                rationale=(f"the claim was discussed but no figure in "
                           f"{unit or 'the same unit'} was given, so the "
                           f"number itself remains unestablished"),
                confidence=0.3, evidence_ids=ev_ids)
        if any(abs(n - target) <= max(0.1 * target, 0.5) for n in numbers):
            supported_by = {getattr(e, "evidence_kind", "") for e in evidence}
            strong = "QUANTIFIED_OUTCOME" in supported_by
            return Verification(
                claim_id=claim_id,
                verdict=SUPPORTED if strong else PARTIALLY_SUPPORTED,
                established_text=f"{target:g}{getattr(claim,'quantity_unit','') or ''}",
                established_value=target,
                established_unit=getattr(claim, "quantity_unit", None),
                rationale=("the candidate restated the figure and supplied a "
                           "baseline, period and attribution"
                           if strong else
                           "the candidate restated the figure but the baseline, "
                           "period or attribution was not established"),
                confidence=0.85 if strong else 0.55, evidence_ids=ev_ids)
        return Verification(
            claim_id=claim_id, verdict=CONTRADICTED,
            established_text=_amount(numbers[0], unit),
            established_value=numbers[0],
            established_unit=unit or None,
            rationale=(
                f"the resume says {_amount(target, unit)} and the interview "
                f"produced {_amount(numbers[0], unit)}. This needs a human to "
                f"resolve; it is not evidence of dishonesty."),
            confidence=0.6, evidence_ids=ev_ids)

    # --- unquantified claims ---------------------------------------------
    supporting = [e for e in evidence if getattr(e, "polarity", "") == "SUPPORTS"]
    if supporting:
        return Verification(
            claim_id=claim_id, verdict=SUPPORTED,
            established_text=None,
            rationale=(f"the candidate spoke to this claim and gave "
                       f"{len(supporting)} piece(s) of supporting detail"),
            confidence=0.6, evidence_ids=ev_ids)
    return Verification(
        claim_id=claim_id, verdict=INSUFFICIENT_EVIDENCE,
        rationale=("the claim came up but the answer did not contain enough "
                   "detail to establish it"),
        confidence=0.3, evidence_ids=ev_ids)
