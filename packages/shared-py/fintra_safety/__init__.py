"""
fintra_safety — reusable AI safety layer shared across every Fintra AI surface.

A deterministic, network-free, dependency-light library that gives every AI surface
in the monorepo (the AI Gateway, the per-package client shims, the streaming tool
copilot, the grounded copilot) two shared capabilities:

  1. INPUT SCREENING for self-harm / suicide intent, returning a compassionate,
     proportional safe response (US 988 Lifeline + emergency + local resources).
     There was previously NO crisis handling anywhere in the repo.

  2. OUTPUT ANNOTATION that appends the right, non-alarming advice disclaimer
     (tax / legal / financial / investment / accounting) so AI output is never
     presented as certain or professional. Idempotent by design.

Usage:

    from fintra_safety import screen_input, annotate_output, guard_completion

    verdict = screen_input(user_text)
    if verdict.crisis:
        return verdict.safe_response          # replace the normal answer

    answer = annotate_output(answer)          # auto-detect advice domains
    answer = annotate_output(answer, domains=["tax"])   # or force one

    # or both at once:
    result = guard_completion(user_text, completion_text)
    return result.text                        # crisis-replaced or disclaimer-annotated

Every function is fail-soft: it coerces bad input and never raises on ordinary
strings, so it can run inline without becoming a new failure mode. Callers should
still wrap the call in try/except as belt-and-suspenders.
"""
from .core import (
    InputVerdict,
    GuardedResult,
    SAFE_DISCLAIMER_MARKER,
    CRISIS_SAFE_RESPONSE,
    DOMAINS,
    screen_input,
    annotate_output,
    guard_completion,
    has_disclaimer,
    uncertainty_note,
    not_verified_evidence_note,
)

__all__ = [
    "InputVerdict",
    "GuardedResult",
    "SAFE_DISCLAIMER_MARKER",
    "CRISIS_SAFE_RESPONSE",
    "DOMAINS",
    "screen_input",
    "annotate_output",
    "guard_completion",
    "has_disclaimer",
    "uncertainty_note",
    "not_verified_evidence_note",
]
