"""Build the interview plan: what to ask this candidate, and why.

WHAT MAKES A PLAN PERSONALISED
Not that an LLM wrote it. A plan is personalised when each competency is
approached through something THIS candidate actually claimed, and the question
quotes them. So every planned competency carries a `hook_claim_id` pointing at
the claim it was built from, and a plan whose hooks are all null is a generic
plan wearing a candidate's name -- which `coverage()` reports rather than hides.

WHAT PERSONALISATION MUST NOT MEAN
Two things, both enforced by tests:

  1. Required competencies do not disappear. If the candidate's materials give
     no hook for `safety_judgement`, the competency is still planned, with the
     rubric's generic question and `candidate_hook = None`. Dropping it because
     the resume was thin would mean the candidates with the least to say get
     assessed on the least.

  2. Irrelevant personal data changes nothing. Name, age, address, school and
     photo are not claims and never become hooks. `test_interview_fairness.py`
     re-plans with only the name changed and asserts the questions are
     identical.

DETERMINISTIC FIRST
The deterministic planner always produces a complete, personalised plan. The
LLM, when configured, may rewrite question WORDING for naturalness -- it does
not choose competencies, weights or hooks. That boundary is deliberate: a model
that can drop a competency can drop the one that mattered, and the failure
would be invisible in the output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from app.interview import claims as C
from app.interview.rubrics import Rubric, RubricCompetency, rubric_for_title

PLANNER_VERSION = "planner-2026.08.29"


@dataclass
class PlannedCompetency:
    competency_key: str
    competency_label: str
    why_it_matters: str
    evidence_needed: str
    initial_question: str
    followup_objectives: List[str]
    role_weight: float
    is_required: bool
    min_evidence_count: int
    max_probe_depth: int
    display_order: int
    candidate_hook: Optional[str] = None
    hook_claim: Optional[C.Claim] = None

    @property
    def is_personalised(self) -> bool:
        return self.hook_claim is not None


@dataclass
class Plan:
    rubric_key: str
    rubric_version: str
    target_minutes: int
    competencies: List[PlannedCompetency]
    generated_by: str = "deterministic"
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    prompt_version: str = PLANNER_VERSION
    fallback_reason: Optional[str] = None

    def coverage(self) -> dict:
        """How much of this plan is actually candidate-specific."""
        total = len(self.competencies)
        personalised = sum(1 for c in self.competencies if c.is_personalised)
        return {
            "competencies": total,
            "personalised": personalised,
            "generic": total - personalised,
            "personalisation_rate": round(personalised / total, 3) if total else 0.0,
            "required_keys": [c.competency_key for c in self.competencies
                              if c.is_required],
        }

    def question_texts(self) -> List[str]:
        return [c.initial_question for c in self.competencies]


# ---------------------------------------------------------------------------
# Question construction from a claim
# ---------------------------------------------------------------------------

def _clean(excerpt: str, limit: int = 150) -> str:
    """Tidy a resume line for quoting back without changing its meaning."""
    s = " ".join((excerpt or "").split())
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s.rstrip(".,;")


#: Read back in the candidate's own casing. "You put 6 years in otr" is a
#: sentence no interviewer would say out loud.
_ACRONYMS = {
    "otr": "OTR", "cdl": "CDL", "ltl": "LTL", "ftl": "FTL", "tl": "TL",
    "hos": "HOS", "eld": "ELD", "bol": "BOL", "pod": "POD", "dot": "DOT",
    "aws": "AWS", "gcp": "GCP", "sql": "SQL", "api": "API", "ci": "CI",
}
#: Bare adjectives that need a noun to read as a phrase: "6 years in regional"
#: is not a sentence; "6 years in regional work" is.
_NEEDS_A_NOUN = {"otr", "regional", "local", "dedicated", "long haul",
                 "short haul", "over the road", "last mile", "final mile"}


def subject_phrase(subject: Optional[str]) -> Optional[str]:
    """The subject as an interviewer would actually say it."""
    s = (subject or "").strip()
    if not s:
        return None
    words = [_ACRONYMS.get(w.lower(), w) for w in s.split()]
    out = " ".join(words)
    if s.lower() in _NEEDS_A_NOUN:
        out += " work"
    return out


def _wants_a_measurement(comp: RubricCompetency) -> bool:
    """Does this competency's evidence actually consist of a number?"""
    need = f"{comp.evidence_needed} {comp.label}".lower()
    return any(w in need for w in
               ("metric", "measur", "number", "baseline", "margin", "rate"))


def question_from_claim(comp: RubricCompetency, claim: C.Claim) -> Optional[str]:
    """A question that quotes the candidate and asks for what is missing.

    The shape is always: what they said -> what specifically is unclear about
    it -> what would establish it. Never "tell me about a time", which asks the
    candidate to pick the example and therefore selects for rehearsal.
    """
    quote = _clean(claim.source_excerpt or claim.claim_text)
    if not quote:
        return None

    t = claim.claim_type

    if t == C.MEASURABLE_OUTCOME and claim.is_quantified:
        unit = claim.quantity_unit or ""
        amount = (f"{claim.quantity_value:,.0f}{unit}"
                  if unit == "%" else
                  f"${claim.quantity_value:,.0f}" if unit == "USD"
                  else f"{claim.quantity_value:,.0f} {unit}")

        # THE METRIC INTERROGATION ONLY BELONGS ON A METRIC COMPETENCY.
        # A dispatcher's exception_handling -- "a specific load that went
        # wrong, who was called, what it cost" -- was asked to explain the
        # baseline and attribution behind an 18% empty-miles figure, because
        # that was the claim left over when the competencies ahead of it had
        # taken theirs. A rich question aimed at the wrong competency gathers
        # no evidence for the thing being assessed and costs a slot.
        if _wants_a_measurement(comp):
            # ONE QUESTION, NOT THREE.
            #
            # This used to ask, in a single breath, what produced the problem
            # before, which part of the fix was theirs, AND how they
            # established the improvement was caused by their change. A person
            # asked three things answers one and the other two are quietly
            # dropped -- so the interview looked rigorous and gathered less.
            #
            # It was also redundant. followup.py already carries a probe for
            # each of the three: the baseline probe ("What was it before?"),
            # the ownership probe ("What was yours specifically?") and the
            # attribution probe ("How did you know it was your change...?").
            # They fire ONLY when the answer has not already covered them,
            # which is the difference between depth that is earned and depth
            # that is recited. Asking everything up front spends that
            # machinery's whole purpose on the first question.
            return (
                f"Your resume says: \"{quote}\". Take me to the {amount} "
                f"itself — what was actually producing that before you "
                f"changed it?")
        # Otherwise the number frames the question and the rubric asks it.
        return f"Your resume says: \"{quote}\". {comp.generic_question}"

    if t == C.LEADERSHIP and claim.is_quantified:
        n = int(claim.quantity_value or 0)
        unit = claim.quantity_unit or "people"
        return (
            f"You mention \"{quote}\". Of those {n} {unit}, how many reported "
            f"to you directly, and what decisions were actually yours to make "
            f"about them — hiring, performance, pay, assignment?")

    if t == C.EQUIPMENT_OPERATED:
        kit = subject_phrase(claim.claim_text) or claim.claim_text
        return (
            f"You list {kit}. Tell me about a specific run on {kit} where "
            f"something went wrong with the equipment or the freight. What "
            f"happened, what did you do first, and who did you call?")

    if t == C.DOMAIN_EXPERIENCE and claim.is_quantified:
        # GROUND IT, THEN ASK THE COMPETENCY'S OWN QUESTION.
        # This used to be a fixed "take the hardest single problem you hit in
        # that time", which is a fine question and has nothing to do with the
        # competency it was generated for. A driver's safety_judgement got it,
        # and the rubric's far better opener -- "a time conditions or the
        # equipment made you decide not to run" -- was thrown away in exchange
        # for looking personalised.
        #
        # Composing keeps both: the tenure is the frame, the rubric asks the
        # question.
        yrs = int(claim.quantity_value or 0)
        subj = subject_phrase(claim.subject)
        frame = (f"You put {yrs} years into {subj}." if subj
                 else f"Your resume says: \"{quote}\".")
        return f"{frame} {comp.generic_question}"

    if t == C.DOMAIN_EXPERIENCE:
        # A BARE LANE MENTION IS NOT A HOOK.
        # "You mention regional work. Walk me through the most difficult
        # situation that came up in that work" was generated for BOTH
        # exception_handling and dispatch_communication in the same driver
        # interview: one template, two nouns, neither serving the competency.
        # The rubric's own opener ("walk me through the last time a load went
        # wrong on you") is better in every way, so returning None here is an
        # improvement rather than a loss -- and `coverage()` now reports the
        # plan's personalisation honestly instead of counting these.
        return None

    if t == C.CERTIFICATION:
        return (
            f"You hold {claim.claim_text}. Tell me about a situation on the job "
            f"where that specifically mattered — where not having it would "
            f"have changed what you could do.")

    if t == C.TECHNICAL_CAPABILITY:
        # The question has to serve the COMPETENCY, not just echo the claim.
        # Hooking "Python" onto a design competency and then asking a tooling
        # question produces a personalised-looking question that gathers no
        # evidence for the thing being assessed.
        if comp.key in ("system_design", "problem_solving"):
            return (
                f"You list {claim.claim_text}. Take something you designed with "
                f"it — what structure did you choose, what was the alternative "
                f"you rejected, and what would you change if the load were ten "
                f"times bigger?")
        if comp.key in ("collaboration", "communication"):
            return (
                f"You list {claim.claim_text}. Tell me about a time you had to "
                f"bring someone else up to speed on it, or defend a choice you "
                f"made with it to someone who disagreed.")
        return (
            f"You list {claim.claim_text}. Describe something you built with it "
            f"where you hit a limit of the tool itself. What was the limit and "
            f"what did you do about it?")

    if t in (C.PROJECT, C.RESPONSIBILITY):
        return (
            f"You mention \"{quote}\". Walk me through what you personally "
            f"decided and did there, and what you would do differently now.")

    return None


def _followup_objectives(comp: RubricCompetency,
                         claim: Optional[C.Claim]) -> List[str]:
    """What still has to be established after the opening question lands."""
    objectives = [f"establish {comp.evidence_needed}"]
    if claim is None:
        objectives.append(
            "get one concrete, named example rather than a general description")
        return objectives

    if claim.is_quantified and claim.claim_type == C.MEASURABLE_OUTCOME:
        objectives += [
            "establish the baseline the number is measured against",
            "establish the time period and the denominator",
            "separate the candidate's contribution from the team's",
            "establish how the improvement was attributed to the change",
        ]
    elif claim.claim_type == C.LEADERSHIP:
        objectives += [
            "separate direct reports from wider project influence",
            "get one specific difficult personnel situation they handled",
        ]
    elif claim.claim_type in (C.EQUIPMENT_OPERATED, C.CERTIFICATION):
        objectives += [
            "confirm hands-on recency, not just exposure",
            "get one situation where it went wrong",
        ]
    else:
        objectives += [
            "get one specific instance with names, dates or numbers",
            "establish what the candidate personally owned",
        ]
    objectives.append("probe one limit, failure or thing they would change")
    return objectives


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def build_plan(*, job_title: str, candidate_claims: Sequence[C.Claim],
               rubric: Optional[Rubric] = None,
               role_config: Optional[dict] = None) -> Plan:
    """Produce a complete, personalised, deterministic plan.

    `role_config` is the recruiter's configuration and OVERRIDES the rubric:
    extra required competencies, weights and must-ask questions. It can add a
    requirement and change a weight. It cannot remove a rubric competency that
    the rubric marks required -- see `_apply_role_config`.
    """
    rubric = rubric or rubric_for_title(job_title)
    cfg = role_config or {}

    used_claim_ids: set[int] = set()
    planned: List[PlannedCompetency] = []

    for order, comp in enumerate(rubric.competencies):
        hook: Optional[C.Claim] = None
        question = comp.generic_question

        # Pick the best unused claim of a type that suits this competency.
        for candidate_claim in C.hooks_for(candidate_claims,
                                           comp.hook_claim_types, limit=6):
            if id(candidate_claim) in used_claim_ids:
                continue
            built = question_from_claim(comp, candidate_claim)
            if built:
                hook = candidate_claim
                question = built
                used_claim_ids.add(id(candidate_claim))
                break

        planned.append(PlannedCompetency(
            competency_key=comp.key,
            competency_label=comp.label,
            why_it_matters=comp.why_it_matters,
            evidence_needed=comp.evidence_needed,
            initial_question=question,
            followup_objectives=_followup_objectives(comp, hook),
            role_weight=comp.weight,
            is_required=comp.required,
            min_evidence_count=comp.min_evidence,
            max_probe_depth=comp.max_probe_depth,
            display_order=order,
            candidate_hook=(_clean(hook.source_excerpt) if hook else None),
            hook_claim=hook,
        ))

    plan = Plan(
        rubric_key=rubric.key,
        rubric_version=rubric.version,
        target_minutes=int(cfg.get("target_minutes") or rubric.target_minutes),
        competencies=planned,
    )
    _apply_role_config(plan, cfg, rubric)
    return plan


def _apply_role_config(plan: Plan, cfg: dict, rubric: Rubric) -> None:
    """Recruiter configuration, applied so it can add but not silently remove.

    A hiring manager may raise a weight, mark something required, or add a
    must-ask question. Marking a rubric-required competency as not-required is
    refused: that is the one edit that would let a role quietly stop being
    assessed on the thing the rubric says it must be.
    """
    weights: Dict[str, float] = cfg.get("competency_weights") or {}
    required: List[str] = list(cfg.get("required_competencies") or [])
    # A real recruiter need: "we do not assess collaboration for this role".
    # Allowed for competencies the rubric marks optional, and refused for the
    # ones it does not -- which is what makes the guard below load-bearing.
    optional: List[str] = list(cfg.get("optional_competencies") or [])

    for comp in plan.competencies:
        if comp.competency_key in weights:
            w = float(weights[comp.competency_key])
            comp.role_weight = max(0.0, min(1.0, w))
        if comp.competency_key in required:
            comp.is_required = True
        if comp.competency_key in optional:
            comp.is_required = False

    # THE GUARD. A rubric-required competency stays required whatever the
    # config asked for.
    #
    # This used to be unreachable: nothing could set is_required=False, so the
    # loop could never fire and a mutation removing it survived. A control that
    # cannot fire is not defence in depth -- it is reassurance. Now that
    # `optional_competencies` exists, this is the thing standing between a
    # hiring manager's convenience and a role quietly stopping being assessed
    # on safety judgement.
    rubric_required = set(rubric.required_keys())
    for comp in plan.competencies:
        if comp.competency_key in rubric_required and not comp.is_required:
            comp.is_required = True
            comp.why_it_matters += (
                " (The role configuration asked for this to be optional. The "
                "rubric marks it required, so it was kept.)")

    # Must-ask questions become their own planned items so the completeness
    # gate covers them like any other requirement.
    for i, q in enumerate(cfg.get("must_ask_questions") or []):
        text = (q or "").strip()
        if not text:
            continue
        plan.competencies.append(PlannedCompetency(
            competency_key=f"must_ask_{i + 1}",
            competency_label=f"Hiring manager question {i + 1}",
            why_it_matters="Asked because the hiring manager requires it.",
            evidence_needed="a direct answer to the question as asked",
            initial_question=text,
            followup_objectives=["get a direct answer to the question as asked"],
            role_weight=float(cfg.get("must_ask_weight", 0.8)),
            is_required=True,
            min_evidence_count=1,
            max_probe_depth=2,
            display_order=100 + i,
        ))
