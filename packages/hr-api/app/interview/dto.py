"""Audience boundaries: what a candidate may receive, and what only staff may.

THE DEFECT THIS REPLACES
The answer endpoint returned the full gap analysis to whoever called it, and
the candidate page "deliberately ignored" it in React. That is not a boundary.
Anyone with DevTools open sees the assessment strategy -- which competency is
being probed, that their last answer read as vague, how much evidence it
produced -- and can then game the rest of the interview. Hiding data in the UI
while shipping it over the wire is a disclosure, not a control.

DENY BY DEFAULT
`candidate_safe()` builds its output from an ALLOWLIST. A new field added to
an internal object does not reach a candidate unless somebody adds its name
here, which is a visible edit in a diff. The opposite design -- strip the
fields we currently consider sensitive -- fails the moment anyone adds a
field, which is the moment nobody is looking.

WHAT A CANDIDATE MAY NEVER SEE
Scores, confidences, gap analysis, evidence counts, competency keys, probe
depth, rubric weights, what evidence is still missing, contradictions found,
recruiter recommendations, and assessment rationale. Several of those are not
obviously sensitive on their own. `probe_depth` is: a candidate who knows they
are on the third follow-up about the same thing learns the system is not
satisfied, which is mid-interview evaluative feedback delivered as an integer.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

#: Everything a candidate is permitted to receive about a question. Note what
#: is missing: competency_id, probe_depth, intent, kind.
QUESTION_FIELDS = ("id", "text", "sequence", "is_followup")

#: About their own answer. No evidence count, no analysis.
ANSWER_FIELDS = ("answer_id", "accepted")

#: About the interview as a whole.
INTERVIEW_FIELDS = ("interview_id", "status", "job_title", "questions_answered",
                    "finished", "message")

#: Names that must never appear anywhere in a candidate payload, at any depth.
#: The adversarial test walks the real response and asserts their absence, so
#: this list is the specification rather than documentation of it.
FORBIDDEN_KEYS = frozenset({
    "score", "overall_score", "confidence", "overall_confidence",
    "gaps", "gap", "missing_evidence", "evidence", "evidence_captured",
    "evidence_ids", "supporting_evidence", "contradicting_evidence",
    "contradictions", "rationale", "assessment", "assessments",
    "competency", "competency_key", "competency_id", "competencies",
    "rubric", "rubric_key", "role_weight", "weight",
    "probe_depth", "intent", "question_kind", "kind",
    "recruiter_view", "recommendation", "recommended_followup",
    "specific", "ownership_clear", "substantive", "is_substantive",
    "strengths", "weaknesses", "verdict", "claim", "claims",
    "hook", "candidate_hook", "why_it_matters", "evidence_needed",
    "state", "completeness_state", "uncovered_required",
})


#: Every key a candidate payload may carry, at any depth. This is the ALLOWLIST
#: the module docstring promises and `candidate_safe` did not have: it refused
#: ~40 known-sensitive names and passed everything else straight through, which
#: is precisely the "strip what we currently consider sensitive" design the
#: docstring warns fails the moment anyone adds a field.
#:
#: The envelope keys are the ones a response wraps its content in; the rest come
#: from the per-object tuples above, so adding a field to a candidate view is one
#: visible edit here rather than an invisible one somewhere else.
CANDIDATE_ENVELOPE_FIELDS = ("finished", "question", "waiting", "reason")

CANDIDATE_ALLOWED_KEYS = frozenset(
    QUESTION_FIELDS + ANSWER_FIELDS + INTERVIEW_FIELDS
    + CANDIDATE_ENVELOPE_FIELDS
)

#: A name on both lists would mean one of them is wrong, and the two controls
#: would disagree about the same field at runtime. Checked at import so it is
#: impossible to ship rather than merely unlikely.
assert not (CANDIDATE_ALLOWED_KEYS & FORBIDDEN_KEYS), (
    "these keys are both allowed and forbidden: "
    f"{sorted(CANDIDATE_ALLOWED_KEYS & FORBIDDEN_KEYS)}")


class AudienceViolation(RuntimeError):
    """A candidate payload contained something only staff may see."""


def _assert_clean(payload: Any, path: str = "") -> None:
    """Walk a payload and refuse anything on the forbidden list.

    Called on the way OUT, not just asserted in a test, because the cost of a
    leak here is a candidate who can reverse-engineer the scoring.
    """
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            if k in FORBIDDEN_KEYS:
                raise AudienceViolation(
                    f"candidate payload contains {k!r} at {path or 'root'}. "
                    f"That is recruiter-only. Add it to the allowlist "
                    f"deliberately, or do not send it.")
            _assert_clean(v, f"{path}.{k}" if path else k)
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            _assert_clean(v, f"{path}[{i}]")


def _assert_allowed(payload: Any, path: str = "") -> None:
    """Walk a payload and refuse anything NOT on the allowlist.

    This is the deny-by-default half. `_assert_clean` below is not redundant
    with it: that one is the specification of what is sensitive and produces the
    message that says WHY a field may not go out, and it also guards the
    explicitly-built DTOs which never pass through here. This one catches the
    field nobody has thought about yet -- which is the only kind that leaks.
    """
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            here = f"{path}.{k}" if path else k
            if k not in CANDIDATE_ALLOWED_KEYS:
                raise AudienceViolation(
                    f"candidate payload contains {k!r} at {here}, "
                    f"which is not on the candidate allowlist. Add it to "
                    f"CANDIDATE_ALLOWED_KEYS deliberately, or do not send it. "
                    f"Refusing rather than dropping it silently: a field that "
                    f"vanishes is a bug someone debugs later, a field that "
                    f"leaks is one nobody sees.")
            _assert_allowed(v, here)
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            _assert_allowed(v, f"{path}[{i}]")


def _pick(source: Mapping, fields: Iterable[str]) -> Dict[str, Any]:
    return {f: source[f] for f in fields if f in source}


def candidate_question(question) -> Dict[str, Any]:
    """One question, as the candidate sees it.

    `is_followup` is a boolean rather than the kind or the depth. A candidate
    benefits from knowing "this is a deeper question about what you just said"
    -- it is much less unnerving than an apparently new topic. They do not
    benefit from knowing it is FOLLOWUP_OWNERSHIP at depth 2, which tells them
    what the system thinks is missing.
    """
    kind = getattr(question, "question_kind", "") or ""
    out = {
        "id": str(getattr(question, "id", "")),
        "text": getattr(question, "question_text", ""),
        "sequence": getattr(question, "sequence_number", None),
        "is_followup": bool(getattr(question, "probe_depth", 0)) or
                       kind.startswith(("FOLLOWUP", "CLARIFY")),
    }
    _assert_clean(out)
    return out


def candidate_answer_ack(answer) -> Dict[str, Any]:
    """Acknowledgement of an answer. Deliberately almost empty.

    It says the answer was stored. It does not say whether it was any good,
    how much evidence it produced, or what is still missing.
    """
    out = {"answer_id": str(getattr(answer, "id", "")), "accepted": True}
    _assert_clean(out)
    return out


def candidate_state(*, interview, job_title: str, questions_answered: int,
                    finished: bool, message: str = "") -> Dict[str, Any]:
    out = {
        "interview_id": str(getattr(interview, "id", "")),
        "status": "IN_PROGRESS" if not finished else "COMPLETED",
        "job_title": job_title,
        "questions_answered": questions_answered,
        "finished": finished,
        "message": message,
    }
    _assert_clean(out)
    return out


def candidate_safe(payload: Mapping) -> Dict[str, Any]:
    """A hand-built dict, checked BOTH ways before it goes to a candidate.

    Deny by default first (is this key one we have decided a candidate may
    receive?), then the sensitive-name check (is it one we have decided they may
    never receive?). The first catches the field nobody has considered; the
    second says why, for the fields we have.
    """
    _assert_allowed(payload)
    _assert_clean(payload)
    return dict(payload)
