"""Interview Fairness service — bias detection, inappropriate-question detection,
protected-class topic warnings, scorecard evidence requirements.

This is the guardrail layer of the Copilot. It does NOT block the interviewer
— it surfaces calm, calibrated warnings inline so a human can self-correct.

Detection categories (transparent, deterministic — every rule documented):
  1. Protected-class probing  (age, family status, religion, etc.)
  2. Subjective-only language (no role-tied evidence)
  3. Inconsistent-criteria language across candidates
  4. Comparative phrasing that anchors to a previous candidate
  5. Trivia / non-job-related screening
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Lexicons — kept transparent so a fairness reviewer can audit them
# ---------------------------------------------------------------------------
# Each lexicon → category. Phrases are lower-cased, word-boundary matched.
_PROTECTED_PATTERNS = [
    (re.compile(r"\b(how\s+old|what\s+(?:year|age)|when\s+(?:did|were)\s+you\s+(?:graduate|born))\b", re.IGNORECASE),
     "age",
     "Avoid questions about age or graduation year unless directly job-related."),
    (re.compile(
        r"\b(are\s+you\s+(?:married|single)"
        r"|family\s+status"
        r"|(?:start|starting|plan\w*\s+to\s+start)\s+a\s+family"
        r"|having\s+(?:any\s+)?(?:kids?|children)"
        r"|kids?|children"
        r"|pregnan\w*|maternity|paternity)\b", re.IGNORECASE),
     "family_status",
     "Family status, pregnancy and childcare are protected categories — avoid."),
    (re.compile(r"\b(what\s+(?:religion|church|temple|mosque)|do\s+you\s+(?:pray|fast|observe))\b", re.IGNORECASE),
     "religion",
     "Religion and observance practices are protected — do not probe."),
    (re.compile(r"\b(where\s+(?:were\s+you\s+born|are\s+you\s+from)|country\s+of\s+origin|native\s+language|first\s+language)\b", re.IGNORECASE),
     "national_origin",
     "National origin and native language are protected — focus on work authorisation if relevant."),
    (re.compile(r"\b(disabilit\w*|disabled|medical\s+condition|mental\s+health|therapy|medication)\b", re.IGNORECASE),
     "disability",
     "Disability and medical status are protected — instead, ask about ability to perform job functions."),
    (re.compile(r"\b(sexual\s+orientation|gay|lesbian|gender\s+identity|trans)\b", re.IGNORECASE),
     "lgbtq",
     "Sexual orientation and gender identity are protected — do not probe."),
    (re.compile(r"\b(arrest|criminal\s+(?:record|history)|conviction)\b", re.IGNORECASE),
     "criminal_history",
     "Criminal-history questions are tightly regulated (ban-the-box). Use HR-approved language only."),
]

_SUBJECTIVE_PATTERNS = [
    (re.compile(r"\b(felt\s+off|bad\s+vibes?|just\s+(?:not|didn'?t)\s+(?:feel|click)|culture\s+fit|not\s+a\s+culture\s+fit|gut\s+feel)\b", re.IGNORECASE),
     "Subjective rationale detected — tie this to a specific job-related signal or evidence."),
    (re.compile(r"\b(too\s+(?:assertive|quiet|aggressive|nice|harsh|emotional|young|old))\b", re.IGNORECASE),
     "'Too X' phrasing tends to encode bias — restate with concrete observed behaviour."),
    (re.compile(r"\b(reminds?\s+me\s+of)\b", re.IGNORECASE),
     "Comparison to past hires can anchor — assess against the rubric, not a memory."),
]

_COMPARATIVE_PATTERNS = [
    (re.compile(r"\b(better|worse|stronger|weaker)\s+than\s+(?:the\s+)?(?:last|previous|other)\s+candidate\b", re.IGNORECASE),
     "Comparative anchoring — score against the rubric independently before comparing."),
]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class FairnessFlag:
    severity: str       # info | warn | block
    category: str       # protected_class | subjective | comparative | evidence_gap
    title: str
    detail: str
    span: Optional[str] = None  # the matched snippet, if any
    rule_id: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def check_question(text: str) -> list[FairnessFlag]:
    """Flag an interviewer question or note for fairness concerns."""
    flags: list[FairnessFlag] = []
    if not text or not text.strip():
        return flags

    for pattern, category, note in _PROTECTED_PATTERNS:
        m = pattern.search(text)
        if m:
            flags.append(FairnessFlag(
                severity="warn",
                category=f"protected_class:{category}",
                title=f"Protected-class topic: {category.replace('_', ' ')}",
                detail=note,
                span=m.group(0),
                rule_id=f"PC-{category}",
                suggestion="Rephrase to focus on a job-related, observable skill.",
            ))

    for pattern, note in _SUBJECTIVE_PATTERNS:
        m = pattern.search(text)
        if m:
            flags.append(FairnessFlag(
                severity="info",
                category="subjective",
                title="Subjective language",
                detail=note,
                span=m.group(0),
                rule_id="SUBJ-1",
                suggestion="Anchor the observation to a competency in the scorecard.",
            ))

    for pattern, note in _COMPARATIVE_PATTERNS:
        m = pattern.search(text)
        if m:
            flags.append(FairnessFlag(
                severity="info",
                category="comparative",
                title="Comparative anchoring",
                detail=note,
                span=m.group(0),
                rule_id="COMP-1",
                suggestion="Score independently before comparing.",
            ))
    return flags


def check_scorecard_note(text: str, *, evidence_snippets: Optional[list[str]] = None) -> list[FairnessFlag]:
    """Score the note for evidence-grounding + subjective markers."""
    flags = check_question(text)
    # Evidence-gap rule: long subjective note with no transcript-cited evidence
    word_count = len((text or "").split())
    if word_count >= 12 and not (evidence_snippets or []):
        flags.append(FairnessFlag(
            severity="warn",
            category="evidence_gap",
            title="Rating without transcript evidence",
            detail="This note is substantive but no transcript snippet is cited as evidence.",
            rule_id="EVID-1",
            suggestion="Click a transcript line to attach evidence before submitting.",
        ))
    return flags


def fairness_summary(flags: list[FairnessFlag]) -> dict:
    """Roll up a list of flags into a panel-debrief friendly digest."""
    by_severity: dict[str, int] = {"info": 0, "warn": 0, "block": 0}
    by_category: dict[str, int] = {}
    for f in flags:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_category[f.category] = by_category.get(f.category, 0) + 1
    return {
        "total": len(flags),
        "by_severity": by_severity,
        "by_category": by_category,
        "highest_severity": "block" if by_severity["block"] > 0 else "warn" if by_severity["warn"] > 0 else "info" if by_severity["info"] > 0 else "none",
    }
