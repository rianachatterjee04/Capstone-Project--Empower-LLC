"""Role rubrics: what a given job is actually assessed on.

WHY RUBRICS ARE DATA AND NOT PROMPTS
A rubric decides what a hiring decision rests on. If it lives inside a prompt
string it cannot be versioned, diffed, weighted by a hiring manager, or shown
to a candidate who asks what they were assessed against. So it is a structured
object with a version, and the version is written onto every plan and scorecard
that used it.

WHAT IS DELIBERATELY ABSENT
There is no dimension here for appearance, confidence, polish, "culture fit",
enthusiasm, communication STYLE, accent, or anything a camera can see. The
dimensions are about what the candidate has done and can explain. That is not
only a fairness position -- it is the only kind of dimension that evidence from
a transcript can actually support.

`communication` is present, and it is scoped narrowly on purpose: whether the
candidate can make a technical or operational point land. Not how they sound.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

RUBRIC_VERSION = "2026.08.29"


@dataclass(frozen=True)
class RubricCompetency:
    key: str
    label: str
    why_it_matters: str
    #: What would have to be in the transcript for this to be assessable.
    evidence_needed: str
    #: A generic opener, used only when the candidate has no relevant claim to
    #: hook onto. A plan that falls back to this for every competency was not
    #: personalised, and `planner` records that.
    generic_question: str
    weight: float = 1.0
    required: bool = True
    min_evidence: int = 1
    max_probe_depth: int = 3
    #: Claim types that make a good personalised hook for this competency.
    hook_claim_types: tuple = ()


#: What vocabulary this role lives in. Follow-up probes read very
#: differently to a driver and to a broker, and "what did you build" is a
#: software question that should never reach either of them.
DOMAIN_DRIVER = "trucking_driver"
DOMAIN_FREIGHT_OFFICE = "trucking_office"
DOMAIN_SOFTWARE = "software"
DOMAIN_GENERAL = "general"


@dataclass(frozen=True)
class Rubric:
    key: str
    label: str
    version: str
    competencies: List[RubricCompetency]
    target_minutes: int = 30
    domain: str = DOMAIN_GENERAL

    def required_keys(self) -> List[str]:
        return [c.key for c in self.competencies if c.required]

    def get(self, key: str) -> Optional[RubricCompetency]:
        for c in self.competencies:
            if c.key == key:
                return c
        return None


# ---------------------------------------------------------------------------
# Shared dimensions. Most roles want these; the role-specific rubrics add to
# them rather than restating them.
# ---------------------------------------------------------------------------

_EVIDENCE_SPECIFICITY = RubricCompetency(
    key="evidence_specificity",
    label="Specificity and evidence",
    why_it_matters=(
        "A candidate who can name systems, numbers, dates and people is "
        "describing something they did. A candidate who cannot may still have "
        "done it, but the interview has not established that."),
    evidence_needed=(
        "at least one concrete example with named specifics, rather than a "
        "description of how they generally approach things"),
    generic_question=(
        "Pick one thing from the last year you'd point to as your best work. "
        "Walk me through what it was and what you specifically did."),
    weight=0.9,
    hook_claim_types=("PROJECT", "MEASURABLE_OUTCOME"),
)

_OWNERSHIP = RubricCompetency(
    key="ownership",
    label="Ownership",
    why_it_matters=(
        "Teams accomplish things; the question is what this person did. This "
        "is not scepticism -- separating personal contribution from team "
        "outcome is the only way to assess an individual from a group result."),
    evidence_needed=(
        "a clear account of what the candidate personally decided, built or "
        "handled, distinct from what the team did"),
    generic_question=(
        "Tell me about something you owned end to end -- where if you hadn't "
        "done it, it wouldn't have happened."),
    weight=1.0,
    hook_claim_types=("LEADERSHIP", "PROJECT", "RESPONSIBILITY"),
)

_PROBLEM_SOLVING = RubricCompetency(
    key="problem_solving",
    label="Problem solving and judgement",
    why_it_matters=(
        "Most roles are not hard because the tasks are hard; they are hard "
        "because the tradeoffs are unclear. This asks whether the candidate "
        "reasons about alternatives rather than executing the first idea."),
    evidence_needed=(
        "a decision with at least one alternative the candidate considered and "
        "rejected, and why"),
    generic_question=(
        "Describe a decision you made where the obvious answer turned out to "
        "be wrong. What did you do instead?"),
    weight=1.0,
    hook_claim_types=("PROJECT", "TECHNICAL_CAPABILITY", "DOMAIN_EXPERIENCE"),
)

_COMMUNICATION = RubricCompetency(
    key="communication",
    label="Communication of ideas",
    why_it_matters=(
        "Whether a technical or operational point lands with the person who "
        "needs it. This is about the CONTENT reaching the listener -- not "
        "about accent, fluency, pace, or how polished the delivery is."),
    evidence_needed=(
        "an explanation that stays accurate while being pitched at a stated "
        "audience, or an account of a message that had to be adjusted"),
    generic_question=(
        "Tell me about a time you had to explain something complicated to "
        "someone who needed to act on it but didn't share your background."),
    weight=0.7,
    required=False,
    hook_claim_types=("RESPONSIBILITY", "LEADERSHIP"),
)

_COLLABORATION = RubricCompetency(
    key="collaboration",
    label="Collaboration and conflict",
    why_it_matters=(
        "Disagreement is normal and constant. What matters is whether the "
        "candidate can describe a real one and what they did about it."),
    evidence_needed=(
        "a specific disagreement or difficult working relationship, and the "
        "candidate's own part in resolving or failing to resolve it"),
    generic_question=(
        "Tell me about a time you disagreed with someone you had to keep "
        "working with. How did it end up?"),
    weight=0.7,
    required=False,
    hook_claim_types=("LEADERSHIP", "RESPONSIBILITY"),
)


# ---------------------------------------------------------------------------
# Role flavour
# ---------------------------------------------------------------------------
# The shared dimensions above are the right THINGS to assess for nearly every
# role. Their openers were not. A CDL driver and a backend engineer were asked
# "tell me about something you owned end to end" in identical words, which is
# how an interview announces that nothing about it was built for the person
# sitting in it.
#
# So a shared competency can be re-worded per role. The key, the weight, the
# evidence required and the required flag are untouched -- only the sentence
# the candidate hears changes. Rewording is presentation. Changing what is
# assessed would be a different rubric, and `_asked_as` cannot do it.


def _asked_as(comp: RubricCompetency, question: str,
              *, hooks: Optional[tuple] = None,
              evidence: Optional[str] = None) -> RubricCompetency:
    """The same competency, asked in this role's language.

    `evidence` is worded per role for the same reason the question is: it is
    printed in the recruiter debrief under "still needed", so the shared
    ownership wording -- "what the candidate personally decided, BUILT or
    handled" -- put a software verb in front of a recruiter hiring a
    dispatcher. What is being ASSESSED is identical; only the sentence
    changes.
    """
    changes = {"generic_question": question}
    if hooks is not None:
        changes["hook_claim_types"] = hooks
    if evidence is not None:
        changes["evidence_needed"] = evidence
    return replace(comp, **changes)


_OWNERSHIP_EVIDENCE_OPS = (
    "a clear account of what the candidate personally decided or handled, "
    "distinct from what the rest of the operation did")


# --- driver ----------------------------------------------------------------
_OWNERSHIP_DRIVER = _asked_as(_OWNERSHIP, (
    "Tell me about a load where, if you had not handled it the way you did, "
    "it would have gone bad. What did you do that nobody told you to do?"),
    evidence=_OWNERSHIP_EVIDENCE_OPS)
_EVIDENCE_DRIVER = _asked_as(_EVIDENCE_SPECIFICITY, (
    "Take one run from the last year you would want a dispatcher to know "
    "about. Where did it start, where did it end, and what happened on it?"))

# --- dispatcher ------------------------------------------------------------
_OWNERSHIP_DISPATCH = _asked_as(_OWNERSHIP, (
    "Tell me about a load that only got covered because you did something "
    "about it. What did you do that was not strictly your job?"),
    evidence=_OWNERSHIP_EVIDENCE_OPS)
_EVIDENCE_DISPATCH = _asked_as(_EVIDENCE_SPECIFICITY, (
    "Take one week from the last year you would point to. How many loads, how "
    "many trucks, and what went wrong in it?"))
_PROBLEM_DISPATCH = _asked_as(_PROBLEM_SOLVING, (
    "Describe a covering decision where the obvious answer turned out to be "
    "wrong. What did you do instead, and what did it cost?"))
_COMMUNICATION_DISPATCH = _asked_as(_COMMUNICATION, (
    "Tell me about a time you had to tell a customer something they did not "
    "want to hear about their freight. How did you put it?"))

# --- broker ----------------------------------------------------------------
_OWNERSHIP_BROKER = _asked_as(_OWNERSHIP, (
    "Tell me about an account that exists because of you. What did you "
    "personally do to open it, and what keeps it?"),
    evidence=_OWNERSHIP_EVIDENCE_OPS)
_EVIDENCE_BROKER = _asked_as(_EVIDENCE_SPECIFICITY, (
    "Take one lane you know cold. What does it pay, what does it cost you to "
    "cover, and how do you know those numbers are right?"))
_PROBLEM_BROKER = _asked_as(_PROBLEM_SOLVING, (
    "Describe a load where the obvious carrier or the obvious rate turned out "
    "to be the wrong call. What did you do instead?"))
_COMMUNICATION_BROKER = _asked_as(_COMMUNICATION, (
    "Tell me about a rate increase you had to explain to a shipper. What did "
    "you actually show them?"))


# ---------------------------------------------------------------------------
# Role rubrics
# ---------------------------------------------------------------------------

SOFTWARE_ENGINEER = Rubric(
    key="software_engineer",
    label="Software engineer",
    version=RUBRIC_VERSION,
    target_minutes=35,
    competencies=[
        RubricCompetency(
            key="technical_depth",
            label="Technical depth",
            why_it_matters=(
                "Whether the candidate understands the systems they have "
                "worked on below the level of the interface."),
            evidence_needed=(
                "an explanation of how something worked internally, including "
                "a failure mode or limit they know about first-hand"),
            generic_question=(
                "Take the most complex system you've worked on. How did it "
                "actually work, and where would it break first?"),
            weight=1.0, max_probe_depth=4,
            hook_claim_types=("MEASURABLE_OUTCOME", "PROJECT",
                              "TECHNICAL_CAPABILITY", "SKILL"),
        ),
        RubricCompetency(
            key="system_design",
            label="Design and tradeoffs",
            why_it_matters=(
                "Senior work is choosing between defensible options under "
                "constraints that are not written down."),
            evidence_needed=(
                "an architectural choice with the alternatives weighed and the "
                "constraint that decided it"),
            generic_question=(
                "Describe an architecture decision you made. What else did you "
                "consider, and what made you pick the one you picked?"),
            weight=0.9, required=False,
            hook_claim_types=("PROJECT", "MEASURABLE_OUTCOME",
                              "TECHNICAL_CAPABILITY"),
        ),
        _PROBLEM_SOLVING, _OWNERSHIP, _EVIDENCE_SPECIFICITY,
        _COMMUNICATION, _COLLABORATION,
    ],
    domain=DOMAIN_SOFTWARE,
)

# --- trucking / 3PL roles, used by the trucking POC ------------------------

CDL_DRIVER = Rubric(
    key="cdl_driver",
    label="CDL driver",
    version=RUBRIC_VERSION,
    target_minutes=25,
    competencies=[
        RubricCompetency(
            key="equipment_experience",
            label="Equipment and freight experience",
            why_it_matters=(
                "Reefer, flatbed, tanker and dry van are different jobs. What "
                "a driver has actually run determines what they can be "
                "dispatched on next week."),
            evidence_needed=(
                "specific equipment operated, for how long, and on what kind "
                "of freight and lanes"),
            generic_question=(
                "What equipment have you run, and what kind of freight?"),
            weight=1.0,
            hook_claim_types=("EQUIPMENT_OPERATED", "DOMAIN_EXPERIENCE", "ROLE_HISTORY"),
        ),
        RubricCompetency(
            key="safety_judgement",
            label="Safety judgement",
            why_it_matters=(
                "The situations that matter are the ones where the safe choice "
                "costs time or money. This asks about a real one, not about "
                "whether they know the rules."),
            evidence_needed=(
                "a specific situation where the candidate chose to stop, "
                "refuse, or delay, and what happened as a result"),
            generic_question=(
                "Tell me about a time conditions or the equipment made you "
                "decide not to run. What did you do and who did you tell?"),
            weight=1.0, max_probe_depth=4,
            hook_claim_types=("DOMAIN_EXPERIENCE", "ROLE_HISTORY"),
        ),
        RubricCompetency(
            key="exception_handling",
            label="Breakdowns, delays and detention",
            why_it_matters=(
                "Loads go wrong. What a driver does in the first thirty "
                "minutes decides whether it becomes a claim, a detention "
                "charge, or nothing."),
            evidence_needed=(
                "a specific breakdown, late appointment, detention or refused "
                "load, including who the candidate contacted and how it was "
                "documented"),
            generic_question=(
                "Walk me through the last time a load went wrong on you. What "
                "happened, what did you do, and how did it get documented?"),
            weight=1.0,
            hook_claim_types=("DOMAIN_EXPERIENCE", "RESPONSIBILITY"),
        ),
        RubricCompetency(
            key="compliance_awareness",
            label="Compliance and inspections",
            why_it_matters=(
                "Hours, logs, inspections and credentials are the difference "
                "between a driver who can be assigned and one who cannot."),
            evidence_needed=(
                "a real inspection or compliance situation and how the "
                "candidate handled the paperwork side of it"),
            generic_question=(
                "Tell me about a DOT inspection you've been through. What did "
                "they look at and how did it go?"),
            weight=0.9,
            hook_claim_types=("CERTIFICATION", "DOMAIN_EXPERIENCE"),
        ),
        RubricCompetency(
            key="dispatch_communication",
            label="Communication with dispatch and customers",
            why_it_matters=(
                "A driver who calls early turns a problem into a plan. One who "
                "calls late turns it into a claim."),
            evidence_needed=(
                "a specific instance of raising a problem before it became "
                "one, or of handling a difficult receiver"),
            generic_question=(
                "Tell me about a difficult delivery or receiver. How did you "
                "handle it and what did you tell dispatch?"),
            weight=0.8,
            hook_claim_types=("RESPONSIBILITY", "DOMAIN_EXPERIENCE"),
        ),
        _OWNERSHIP_DRIVER, _EVIDENCE_DRIVER,
    ],
    domain=DOMAIN_DRIVER,
)

DISPATCHER = Rubric(
    key="dispatcher",
    label="Dispatcher",
    version=RUBRIC_VERSION,
    target_minutes=30,
    competencies=[
        RubricCompetency(
            key="load_planning",
            label="Load planning and coverage",
            why_it_matters=(
                "Covering freight profitably under equipment and hours "
                "constraints is the job."),
            evidence_needed=(
                "a specific week or day where coverage was tight and what the "
                "candidate traded off"),
            generic_question=(
                "Describe a day where you were short on trucks or drivers. "
                "How did you decide what got covered?"),
            weight=1.0,
            hook_claim_types=("RESPONSIBILITY", "DOMAIN_EXPERIENCE", "MEASURABLE_OUTCOME"),
        ),
        RubricCompetency(
            key="exception_handling",
            label="Exception handling",
            why_it_matters=(
                "Detention, breakdowns and missed appointments all have a "
                "financial consequence that depends on how fast someone acts."),
            evidence_needed=(
                "a specific exception, the actions taken, and the commercial "
                "outcome"),
            generic_question=(
                "Tell me about a load that went badly wrong. What did it end "
                "up costing and what did you do?"),
            weight=1.0,
            hook_claim_types=("DOMAIN_EXPERIENCE", "MEASURABLE_OUTCOME"),
        ),
        RubricCompetency(
            key="driver_relationships",
            label="Working with drivers",
            why_it_matters=(
                "Dispatchers who cannot keep drivers lose the fleet, and "
                "turnover is the most expensive line in the business."),
            evidence_needed=(
                "a specific difficult conversation with a driver and how it "
                "was handled"),
            generic_question=(
                "Tell me about a driver who was unhappy with you. What was it "
                "about and how did it end?"),
            weight=0.9,
            hook_claim_types=("LEADERSHIP", "RESPONSIBILITY"),
        ),
        _PROBLEM_DISPATCH, _OWNERSHIP_DISPATCH, _EVIDENCE_DISPATCH,
        _COMMUNICATION_DISPATCH,
    ],
    domain=DOMAIN_FREIGHT_OFFICE,
)

FREIGHT_BROKER = Rubric(
    key="freight_broker",
    label="Freight broker",
    version=RUBRIC_VERSION,
    target_minutes=30,
    competencies=[
        RubricCompetency(
            key="carrier_sourcing",
            label="Carrier sourcing and vetting",
            why_it_matters=(
                "Who a broker puts on a load is the single largest risk "
                "decision they make."),
            evidence_needed=(
                "how the candidate qualifies an unfamiliar carrier, with a "
                "specific instance of turning one down"),
            generic_question=(
                "How do you decide whether to use a carrier you haven't worked "
                "with? Tell me about one you rejected."),
            weight=1.0,
            hook_claim_types=("DOMAIN_EXPERIENCE", "RESPONSIBILITY"),
        ),
        RubricCompetency(
            key="margin_discipline",
            label="Margin discipline",
            why_it_matters=(
                "Covering freight is easy at a loss. The job is covering it at "
                "a margin the business can survive."),
            evidence_needed=(
                "a specific load or lane where the candidate held or walked "
                "away from a rate, with the numbers"),
            generic_question=(
                "Tell me about a load you walked away from on price. What were "
                "the numbers and what happened after?"),
            weight=1.0,
            hook_claim_types=("MEASURABLE_OUTCOME", "DOMAIN_EXPERIENCE"),
        ),
        RubricCompetency(
            key="shipper_relationships",
            label="Shipper relationships",
            why_it_matters=(
                "Brokerage is a repeat business; a shipper who calls back is "
                "worth more than a load won on price."),
            evidence_needed=(
                "a specific account the candidate grew or lost, and why"),
            generic_question=(
                "Tell me about an account you grew. What did you do that the "
                "previous broker wasn't doing?"),
            weight=0.9, required=False,
            hook_claim_types=("MEASURABLE_OUTCOME", "ROLE_HISTORY"),
        ),
        _PROBLEM_BROKER, _OWNERSHIP_BROKER, _EVIDENCE_BROKER,
        _COMMUNICATION_BROKER,
    ],
    domain=DOMAIN_FREIGHT_OFFICE,
)

OPERATIONS_MANAGER = Rubric(
    key="operations_manager",
    label="Operations manager",
    version=RUBRIC_VERSION,
    target_minutes=35,
    competencies=[
        RubricCompetency(
            key="operational_control",
            label="Operational control",
            why_it_matters=(
                "Whether the candidate ran the operation or reported on it."),
            evidence_needed=(
                "a metric the candidate personally moved, with the baseline "
                "and the mechanism"),
            generic_question=(
                "What operational number were you responsible for, and what "
                "did it do while you owned it?"),
            weight=1.0, max_probe_depth=4,
            hook_claim_types=("MEASURABLE_OUTCOME", "RESPONSIBILITY"),
        ),
        RubricCompetency(
            key="people_leadership",
            label="People leadership",
            why_it_matters=(
                "Team size is not leadership evidence. What the candidate did "
                "with a struggling or departing person is."),
            evidence_needed=(
                "a specific performance or conflict situation the candidate "
                "handled directly"),
            generic_question=(
                "Tell me about someone on your team who wasn't working out. "
                "What did you actually do?"),
            weight=1.0,
            hook_claim_types=("LEADERSHIP",),
        ),
        _PROBLEM_SOLVING, _OWNERSHIP, _EVIDENCE_SPECIFICITY,
        _COMMUNICATION, _COLLABORATION,
    ],
)

GENERAL = Rubric(
    key="general",
    label="General role",
    version=RUBRIC_VERSION,
    competencies=[_EVIDENCE_SPECIFICITY, _OWNERSHIP, _PROBLEM_SOLVING,
                  _COMMUNICATION, _COLLABORATION],
)


# --- finance and accounting ------------------------------------------------
#
# A staff accountant used to fall through to GENERAL and be asked to "pick one
# thing from the last year you'd point to as your best work" -- a question that
# would suit a marketer, a nurse or a bricklayer equally well. Finance is one
# of the buyers this product is shown to, and the interview it produced for a
# finance candidate was the weakest one in the set.
#
# The competencies below are the ones a controller actually screens for, and
# each names evidence a real accountant can produce and a bluffer cannot: a
# reconciliation that did not tie and what was behind it, a control they
# operated rather than described, and a judgement call with a number attached.
ACCOUNTANT = Rubric(
    key="accountant",
    label="Accountant / finance",
    version=RUBRIC_VERSION,
    target_minutes=35,
    competencies=[
        RubricCompetency(
            key="close_and_reconciliation",
            label="Close and reconciliation",
            why_it_matters=(
                "Anyone can describe a close. The question is what they do "
                "when an account does not tie and the deadline is tomorrow."),
            evidence_needed=(
                "a specific reconciliation that did not tie, what the "
                "difference turned out to be, and how they found it"),
            generic_question=(
                "Tell me about an account that would not reconcile close to a "
                "deadline. What was the difference, and how did you find it?"),
            weight=1.0, max_probe_depth=4,
            hook_claim_types=("MEASURABLE_OUTCOME", "PROJECT", "SKILL"),
        ),
        RubricCompetency(
            key="controls_and_judgement",
            label="Controls and judgement",
            why_it_matters=(
                "A control someone OPERATES is a different thing from a "
                "control they can name, and the difference shows up in an "
                "audit."),
            evidence_needed=(
                "a control they personally operated, and a judgement call "
                "where the accounting answer and the commercial pressure "
                "pointed different ways"),
            generic_question=(
                "Tell me about a time the accounting treatment you believed "
                "was right was not the answer somebody wanted. What did you "
                "do?"),
            weight=0.95, max_probe_depth=3,
            hook_claim_types=("PROJECT", "SKILL", "MEASURABLE_OUTCOME"),
        ),
        RubricCompetency(
            key="audit_and_evidence",
            label="Audit and evidence",
            why_it_matters=(
                "Finance work is defended after the fact. Whether someone "
                "keeps evidence as they go is visible in how they answer."),
            evidence_needed=(
                "a schedule or a workpaper they prepared, and what a reviewer "
                "or an auditor asked about it"),
            generic_question=(
                "Take a schedule you prepared for a reviewer or an auditor. "
                "What did they push back on, and what did you show them?"),
            weight=0.85, required=False,
            hook_claim_types=("PROJECT", "SKILL"),
        ),
        _PROBLEM_SOLVING, _OWNERSHIP, _EVIDENCE_SPECIFICITY,
        _COMMUNICATION, _COLLABORATION,
    ],
    domain=DOMAIN_GENERAL,
)


RUBRICS: Dict[str, Rubric] = {
    r.key: r for r in (SOFTWARE_ENGINEER, CDL_DRIVER, DISPATCHER,
                       FREIGHT_BROKER, OPERATIONS_MANAGER, ACCOUNTANT,
                       GENERAL)
}

#: Title fragments -> rubric. Ordered: the first match wins, so put the
#: specific ones first. "driver" must beat "operations" for "driver operations".
_TITLE_HINTS = (
    ("cdl", "cdl_driver"),
    ("truck driver", "cdl_driver"),
    ("driver", "cdl_driver"),
    ("dispatcher", "dispatcher"),
    ("dispatch", "dispatcher"),
    ("broker", "freight_broker"),
    ("carrier sales", "freight_broker"),
    ("software", "software_engineer"),
    ("engineer", "software_engineer"),
    ("developer", "software_engineer"),
    ("operations manager", "operations_manager"),
    ("ops manager", "operations_manager"),
    # Finance. "controller" and "bookkeeper" before the looser ones, and
    # "account manager" must NOT match here -- that is a sales job.
    ("controller", "accountant"),
    ("accountant", "accountant"),
    ("accounting", "accountant"),
    ("bookkeeper", "accountant"),
    ("financial analyst", "accountant"),
    ("finance manager", "accountant"),
)


def rubric_for_title(title: str) -> Rubric:
    """Pick a rubric from a job title.

    Falls back to GENERAL rather than guessing. A wrong rubric is worse than a
    generic one: it would assess a candidate against competencies their role
    does not have, and the scorecard would look specific while being wrong.
    """
    low = (title or "").lower()
    for fragment, key in _TITLE_HINTS:
        if fragment in low:
            return RUBRICS[key]
    return GENERAL


def domain_for_key(key: Optional[str]) -> str:
    """The vocabulary a stored plan's rubric is interviewed in.

    Falls back to the general lexicon rather than raising: a plan written by an
    older version, or a rubric that has since been renamed, should produce a
    slightly blander interview and not a 500.
    """
    r = RUBRICS.get(key or "")
    return r.domain if r is not None else DOMAIN_GENERAL
