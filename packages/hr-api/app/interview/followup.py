"""Decide the next question from what the last answer left open.

THE JOB
Given an analysis of the answer, the competency being probed, and how deep we
already are, either produce the next probe or decide this competency has what
it needs and move on.

MOVING ON IS A FEATURE, NOT A SHORTCUT
The most common failure of an "adaptive" interviewer is that it always probes.
A candidate who answers completely and then gets asked three more questions
about the same thing learns the system is not listening, and the transcript
fills with redundant evidence that makes the competency look thoroughly
explored when it was answered the first time. `should_stop` exists to prevent
that, and the acceptance test asserts a strong answer produces FEWER follow-ups
than a vague one.

NOT ADVERSARIAL
Every probe below asks for something specific that is missing. None of them
implies the candidate is lying, and the contradiction probe is deliberately
written as "help me line these up" rather than "your resume disagrees with
you". Incomplete evidence is the normal state of a conversation, not a
character finding.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import List, Optional

from app.interview.analysis import AnswerAnalysis
from app.interview.rubrics import (DOMAIN_DRIVER, DOMAIN_FREIGHT_OFFICE,
                                   DOMAIN_GENERAL, DOMAIN_SOFTWARE)

FOLLOWUP_VERSION = "followup-2026.08.29"

# question_kind values, mirroring interview_questions.question_kind
FOLLOWUP_SPECIFIC = "FOLLOWUP_SPECIFIC"
FOLLOWUP_OWNERSHIP = "FOLLOWUP_OWNERSHIP"
FOLLOWUP_METRIC = "FOLLOWUP_METRIC"
FOLLOWUP_TRADEOFF = "FOLLOWUP_TRADEOFF"
FOLLOWUP_FAILURE = "FOLLOWUP_FAILURE"
FOLLOWUP_CONFLICT = "FOLLOWUP_CONFLICT"
CLARIFY_CONTRADICTION = "CLARIFY_CONTRADICTION"


@dataclass
class Followup:
    question_text: str
    question_kind: str
    intent: str
    #: Which gap this probe is trying to close.
    targets_gap: str
    #: The question WITHOUT its acknowledgement.
    #:
    #: The runner refuses to ask the same question twice, and it used to
    #: compare full question text. Once acknowledgements started varying,
    #: "Understood. Can you take me to..." and "Thanks. Can you take me to..."
    #: stopped comparing equal and the same probe went out twice in a row --
    #: the exact behaviour the duplicate guard exists to prevent, reintroduced
    #: by the fix for robotic repetition. The guard compares this instead.
    probe_body: str = ""


@dataclass
class Decision:
    """Either a next probe, or a reason there isn't one."""

    followup: Optional[Followup]
    stop_reason: Optional[str] = None
    #: True when the competency has what it needs and the interview moves on.
    move_on: bool = False

    @property
    def has_followup(self) -> bool:
        return self.followup is not None


# ---------------------------------------------------------------------------
# The vocabulary a role is actually interviewed in
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Lexicon:
    """The nouns a probe uses.

    "What did you personally decide, build or handle" went to a CDL driver and
    to a dispatcher. Neither of them builds anything, and a candidate hearing a
    software word in a trucking interview learns exactly how much of this was
    written for them.
    """
    #: "take me to ONE PARTICULAR RUN"
    instance: str
    #: "what happened on THAT RUN"
    the_work: str
    #: "what did you personally DECIDE OR HANDLE"
    did_verbs: str
    #: who a decision normally has to be justified to in this job
    audience: str


LEXICONS = {
    DOMAIN_DRIVER: Lexicon(
        instance="one particular run", the_work="that run",
        did_verbs="decide or do yourself", audience="dispatch"),
    DOMAIN_FREIGHT_OFFICE: Lexicon(
        instance="one particular load", the_work="that load",
        did_verbs="decide or handle yourself", audience="the customer"),
    DOMAIN_SOFTWARE: Lexicon(
        instance="one particular project", the_work="that project",
        did_verbs="decide, build or handle", audience="the team"),
    DOMAIN_GENERAL: Lexicon(
        instance="one particular instance", the_work="that",
        did_verbs="decide or handle", audience="the people around you"),
}


def lexicon_for(domain: Optional[str]) -> Lexicon:
    return LEXICONS.get(domain or DOMAIN_GENERAL, LEXICONS[DOMAIN_GENERAL])


# ---------------------------------------------------------------------------
# Acknowledgement
# ---------------------------------------------------------------------------

#: Neutral hand-offs. None of them says whether the answer was any good.
_ACKS = ("Got it.", "Okay.", "Right.", "Understood.", "Thanks.")
_ACKS_LONG = ("Thanks — that's helpful detail.", "Okay, there's a lot there.",
              "Right, I follow.")


def _acknowledge(analysis: AnswerAnalysis, *, salt: str = "") -> str:
    """A neutral hand-off into the next question.

    NEVER EVALUATIVE. "Great answer" tells a candidate mid-interview that they
    are doing well, which is both feedback they should not get and information
    they will read into the next question. These acknowledge that the answer
    was HEARD, which is what makes a conversation feel human, without saying
    whether it was good.

    NEVER THE SAME WORD EVERY TIME. This returned the literal string "Got it."
    for every answer under 120 words, so a ten-question interview opened nine
    probes identically. A candidate notices that in about ninety seconds, and
    what they notice is that nothing is listening.

    The choice is deterministic -- crc32, not `hash()`, because `hash()` on a
    string is salted per process and the same interview would replay
    differently. Same answer, same probe, same acknowledgement, every run.
    """
    if analysis.contradicts:
        return "Let me make sure I've got this right."
    pool = _ACKS_LONG if analysis.word_count > 120 else _ACKS
    key = f"{salt}|{analysis.word_count}|{(analysis.gaps or [''])[0]}"
    return pool[zlib.crc32(key.encode("utf-8")) % len(pool)]


# ---------------------------------------------------------------------------
# The probe patterns
# ---------------------------------------------------------------------------

def _contradiction_probe(analysis: AnswerAnalysis, lex: Lexicon,
                         salt: str) -> Followup:
    detail = analysis.contradicts[0]
    body = (f"I want to line two things up — {detail}. Can you walk me "
            f"through how those fit together? I'd rather understand it than "
            f"guess.")
    return Followup(
        question_text=(
            f"{_acknowledge(analysis, salt=salt)} {body}"),
        probe_body=body,
        question_kind=CLARIFY_CONTRADICTION,
        intent="resolve an apparent disagreement neutrally",
        targets_gap="clarify an apparent disagreement with the resume")


def _specificity_probe(analysis: AnswerAnalysis, lex: Lexicon,
                       salt: str) -> Followup:
    if analysis.is_generic_approach:
        # Safe to use the role noun here: the candidate has just described how
        # they generally do the JOB, so "one particular run" is on topic.
        text = (f"That's how you approach it in general. Take me to "
                f"{lex.instance} where you did it — what was the situation, "
                f"and what happened?")
    else:
        # DELIBERATELY DOMAIN-NEUTRAL.
        # This probe fires on any competency, including ones that are not
        # about operating the equipment. "Can you take me to one particular
        # run?" went to a driver talking about a roadside INSPECTION, which is
        # not a run. A role noun applied to the wrong subject reads worse than
        # no role noun at all.
        text = ("Can you take me to one specific time? I'm after one case — "
                "what it was, when, and what you did.")
    return Followup(
        question_text=f"{_acknowledge(analysis, salt=salt)} {text}",
        probe_body=text,
        question_kind=FOLLOWUP_SPECIFIC,
        intent="convert a general description into a specific instance",
        targets_gap="get one concrete, named example")


def _ownership_probe(analysis: AnswerAnalysis, lex: Lexicon,
                     salt: str) -> Followup:
    """Separate the person from the group -- without inventing a group.

    This used to open "You've described what the team did" unconditionally. It
    was put to a dispatcher whose answer was "I call before they call me, with
    a new time I can actually hit", which mentions no team at all. Telling a
    candidate they said something they did not say is worse than a bland
    question, so the opening now depends on whether the answer was actually in
    the team's voice.
    """
    if analysis.team_voice_only:
        lead = "You've described what the team did."
    else:
        lead = f"I want to be clear on your part in {lex.the_work}."
    body = (f"{lead} What was yours specifically — what did you personally "
            f"{lex.did_verbs}?")
    return Followup(
        question_text=f"{_acknowledge(analysis, salt=salt)} {body}",
        probe_body=body,
        question_kind=FOLLOWUP_OWNERSHIP,
        intent="separate individual contribution from team outcome",
        targets_gap="separate what the candidate did from what the team did")


def _metric_probe(gap: str, analysis: AnswerAnalysis, lex: Lexicon,
                  salt: str) -> Followup:
    if "baseline" in gap:
        text = ("What was it before? I'm trying to understand what the number "
                "is measured against.")
        intent = "establish the baseline"
    elif "time period" in gap:
        text = "Over what period did that happen?"
        intent = "establish the measurement window"
    elif "attributed" in gap:
        text = ("How did you know it was your change that did it, rather than "
                "something else moving at the same time?")
        intent = "establish attribution"
    else:
        text = ("Is there a number on that? If it wasn't measured, that's a "
                "fine answer too.")
        intent = "establish whether a measurement exists"
    return Followup(
        question_text=f"{_acknowledge(analysis, salt=salt)} {text}",
        probe_body=text,
        question_kind=FOLLOWUP_METRIC,
        intent=intent, targets_gap=gap)


def _tradeoff_probe(analysis: AnswerAnalysis, lex: Lexicon,
                    salt: str) -> Followup:
    body = ("What else did you consider and decide against? I'm interested in "
            "what made you pick this one.")
    return Followup(
        question_text=f"{_acknowledge(analysis, salt=salt)} {body}",
        probe_body=body,
        question_kind=FOLLOWUP_TRADEOFF,
        intent="surface the rejected alternative and the deciding constraint",
        targets_gap="get the alternative that was considered and rejected")


def _failure_probe(analysis: AnswerAnalysis, lex: Lexicon,
                   salt: str) -> Followup:
    body = ("What didn't go well in that? Or what would you do differently if "
            "you were doing it again?")
    return Followup(
        question_text=f"{_acknowledge(analysis, salt=salt)} {body}",
        probe_body=body,
        question_kind=FOLLOWUP_FAILURE,
        intent="test whether the candidate knows the limits of their own work",
        targets_gap="probe a limit, failure or thing they would change")


def _conflict_probe(analysis: AnswerAnalysis, lex: Lexicon,
                    salt: str) -> Followup:
    body = (f"Did anyone disagree with that call — {lex.audience}, or anyone "
            f"else? How did you handle it?")
    return Followup(
        question_text=f"{_acknowledge(analysis, salt=salt)} {body}",
        probe_body=body,
        question_kind=FOLLOWUP_CONFLICT,
        intent="get a real disagreement rather than a leadership assertion",
        targets_gap="get a specific disagreement and the candidate's part in it")


_GAP_TO_PROBE = (
    ("clarify an apparent disagreement", _contradiction_probe),
    ("get one concrete, named example", _specificity_probe),
    ("separate what the candidate did", _ownership_probe),
    ("establish the baseline",
     lambda a, lex, salt: _metric_probe("baseline", a, lex, salt)),
    ("establish the time period",
     lambda a, lex, salt: _metric_probe("time period", a, lex, salt)),
    ("establish how the result was attributed",
     lambda a, lex, salt: _metric_probe("attributed", a, lex, salt)),
    ("get a number",
     lambda a, lex, salt: _metric_probe("number", a, lex, salt)),
    ("get the alternative", _tradeoff_probe),
    ("probe a limit, failure", _failure_probe),
    ("get a specific disagreement", _conflict_probe),
)


def decide(analysis: AnswerAnalysis, *, probe_depth: int, max_probe_depth: int,
           evidence_count: int, min_evidence: int,
           expects_conflict: bool = False,
           domain: Optional[str] = None,
           competency_key: str = "") -> Decision:
    """Probe again, or move on.

    The order of the stop conditions matters. Depth is checked before gaps,
    because an interview that keeps probing a candidate who cannot give more
    is not gathering evidence -- it is grinding.
    """
    if not analysis.is_substantive:
        # A non-answer gets exactly one gentle re-ask, then the interview
        # moves on. Pressing someone who declined is not assessment.
        if probe_depth == 0:
            lex = lexicon_for(domain)
            _body = (f"No problem. If it helps, we can take it from a "
                     f"different angle — is there {lex.instance} that comes "
                     f"to mind, even a small one?")
            return Decision(followup=Followup(
                question_text=_body, probe_body=_body,
                question_kind=FOLLOWUP_SPECIFIC,
                intent="offer one re-entry after a non-answer",
                targets_gap="the question was not answered"))
        return Decision(followup=None, move_on=True,
                        stop_reason="the candidate did not answer and was "
                                    "asked once more")

    if probe_depth >= max_probe_depth:
        return Decision(followup=None, move_on=True,
                        stop_reason=f"probe depth {max_probe_depth} reached")

    gaps = list(analysis.gaps)
    if not expects_conflict:
        gaps = [g for g in gaps if "disagreement and the candidate" not in g]

    # A strong answer that already carries enough evidence ends the probe. This
    # is the branch that keeps a good candidate from being interrogated.
    if not gaps and evidence_count >= min_evidence:
        return Decision(followup=None, move_on=True,
                        stop_reason="the answer was specific, owned and "
                                    "supported; nothing material is missing")

    if not gaps:
        return Decision(followup=None, move_on=True,
                        stop_reason="no material gap remains in this answer")

    # Diminishing returns: past the first probe, only the two highest-value
    # gap kinds are worth another question.
    if probe_depth >= 2:
        high_value = [g for g in gaps
                      if g.startswith(("clarify an apparent", "separate what"))]
        if not high_value:
            return Decision(followup=None, move_on=True,
                            stop_reason="remaining gaps are not worth another "
                                        "probe at this depth")
        gaps = high_value

    top = gaps[0]
    lex = lexicon_for(domain)
    # The salt is what stops one interview opening every probe with the same
    # word. It is stable input, not randomness: the same competency at the same
    # depth always produces the same acknowledgement.
    salt = f"{competency_key}|{probe_depth}"
    for prefix, builder in _GAP_TO_PROBE:
        if top.startswith(prefix):
            return Decision(followup=builder(analysis, lex, salt))

    return Decision(followup=None, move_on=True,
                    stop_reason=f"no probe pattern for gap {top!r}")
