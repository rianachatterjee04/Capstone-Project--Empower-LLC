"""Read one answer and work out what it did and did not establish.

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR
This drives PROBING. It decides what to ask next. It does not produce a score.

That distinction is the whole reason this module can use linguistic signals at
all. Noticing that an answer says "we" eleven times and "I" never is a
legitimate reason to ask "what did you personally do?" -- it is a bad reason to
mark someone down on ownership. The first is a question; the second would be
scoring someone on grammar.

So: signals here, evidence in `evidence.py`, scores only from evidence. A
candidate whose answer is full of "we" and who then explains exactly what they
did ends up with strong ownership evidence, because the follow-up got the
answer that the first response did not contain.

WHAT IS DELIBERATELY NOT MEASURED
Filler words, hedging, confidence phrasing, sentence length, vocabulary and
speaking rate. The previous implementation scored on `_FILLER_PATTERN` and
`_HEDGE_PATTERN`, which measures fluency and nervousness -- and penalises the
non-native speaker and the anxious candidate for things unrelated to whether
they can do the job.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from app.interview import claims as C

ANALYSIS_VERSION = "analysis-2026.08.29"

# --- signals ---------------------------------------------------------------
# Deliberately narrow. Each one exists to justify a specific follow-up.

# FIRST-PERSON ACTION.
# The first version was a fixed list of verbs -- built, shipped, debugged,
# migrated -- which is software vocabulary. A driver saying "I pulled the
# temperature log, photographed the readout and called dispatch" scored as
# NOT owning their work, because none of those verbs was on the list. That is
# a fairness defect, not a tuning problem: it marks down every candidate whose
# job is not writing software.
#
# So the pattern is now structural rather than lexical: "I" followed by a past
# tense verb, plus the common irregulars. It matches what the candidate DID in
# any domain.
# THE IRREGULAR LIST HAS TO BE COMPLETE ENOUGH TO INCLUDE "DID".
# It was not. "Nobody told me to pull the temperature log; I did it because it
# was the only thing that would stop the load being rejected" -- the clearest
# statement of personal ownership in the whole driver interview -- came back
# with has_first_person_action=False, because the most common past-tense verb
# in English was missing from the list. The engine then asked the candidate to
# separate their contribution from the team's, in an answer that mentions no
# team.
#
# An adverb may also sit between the pronoun and the verb: "I personally
# called", "I never signed it". Without a slot for it the sentence reads as
# no action at all.
_FIRST_PERSON_ACTIVE = re.compile(
    r"\bI\s+"
    r"(?:(?:personally|then|just|already|never|finally|immediately|actually|"
    r"eventually|myself|only|still|also|\w+ly)\s+)?"
    r"(?:(?:re-?)?"
    r"(?:\w+ed"                               # regular past tense
    r"|built|wrote|drove|ran|took|made|kept|put|got|went|had|held|found|"
    r"caught|brought|taught|sent|told|chose|drew|broke|spoke|stood|shut|"
    r"hit|led|left|lost|met|paid|read|said|saw|set|sat|sold|won|dealt|"
    r"rewrote|shipped|swore|rode|threw|understood|"
    r"did|gave|came|knew|thought|felt|spent|began|cut|let|quit|ate|flew|"
    r"grew|wore|hurt|swept|woke|bought|fought|sought|dug|hung|slid|split|"
    r"stuck|struck|swam|tore|wound|bet|burst|cast|cost|fed|fled|forgot|"
    r"froze|ground|laid|lent|lit|rang|rose|sank|shook|shone|shot|sprang|"
    r"stole|stung|sweat|threw|woke|wrung"
    r"))\b"
    # AN EMPTY PREDICATE IS NOT AN ACTION.
    # Admitting "did" to the verb list (see above) also admitted "I did
    # pretty well", which names nothing the candidate actually did. The
    # exclusion is deliberately short: these are the phrases that describe a
    # RESULT in place of an action.
    r"(?!\s+(?:pretty\s+|really\s+|quite\s+|very\s+)?"
    r"(?:well|fine|ok|okay|alright|great|badly|poorly|good|my\s+best|"
    r"a\s+good\s+job|fun)\b)",
    re.IGNORECASE)

# "THEY" IS NOT TEAM VOICE.
# It was in this pattern, and it matches the most common third-person pronoun
# in English regardless of who it refers to. A dispatcher answering "I call
# before they call me, with a new time I can actually hit" -- where "they" is
# the CUSTOMER -- was recorded as speaking in the team's voice and then told
# "you've described what the team did".
#
# What this pattern is for is an answer that attributes the work to a group
# the candidate was part of. That is first-person plural.
_TEAM_VOICE = re.compile(
    r"\b(?:we|us|our team|our group|the team|the group|the crew|"
    r"everyone|the department)\b", re.IGNORECASE)

#: Any quantity, counted for density. Years excluded for the same reason as
#: below: a date is not a measurement.
_BARE_QUANTITY = re.compile(r"\b(?!(?:19|20)\d{2}\b)\d+(?:[.,]\d+)?%?")

#: A number that is not a year. Years are dates, not measurements.
_NUMBER = re.compile(r"\b(?!(?:19|20)\d{2}\b)\d+(?:[.,]\d+)?\s*"
                     r"(?:%|percent|k\b|m\b|x\b|hours?|days?|weeks?|months?|"
                     r"minutes?|seconds?|ms\b|loads?|miles?|people|reports?)?")

#: A number that is being offered as an OUTCOME -- an improvement, a rate, a
#: score -- rather than as a description of the thing being discussed.
_OUTCOME_NUMBER = re.compile(
    r"(?:\b(?:reduc\w+|cut|drop\w*|decreas\w+|lower\w+|improv\w+|increas\w+|"
    r"grew|rais\w+|sav\w+|boost\w+|went from|down to|up to|averag\w+|"
    r"rate of|on[- ]time|uptime|margin)\b[^.\n]{0,40}?\d"
    r"|\d+(?:\.\d+)?\s*(?:%|percent)"
    r"|\d[^.\n]{0,25}?\b(?:per (?:week|month|day|year|hour)|a (?:week|month|day))\b)",
    re.IGNORECASE)

_BASELINE = re.compile(
    r"\b(?:from|was|used to be|previously|before|baseline|down from|up from|"
    r"started at|had been)\b", re.IGNORECASE)

# TIMEFRAME.
# An ordinal or relative word may sit between the preposition and the unit:
# "over the following quarter", "in the next two sprints". Missing those made
# a fully-supported answer look like it had no time period and produced a
# redundant probe.
#
# It also missed the way operations people actually name a period. "empty
# miles from 22% to 18% between Q2 and Q4" -- a baseline, an outcome and a
# window in sixteen words -- was recorded as CONTRADICTS / UNSUPPORTED_METRIC,
# because "between" was not a preposition it knew and "Q2" was not a unit. The
# most precise answer in the interview became evidence against the candidate.
_TIMEFRAME = re.compile(
    r"\b(?:"
    # over/in/across/between two quarters, the following month, 6 weeks
    r"(?:over|within|in|across|during|per|throughout|between|after|for|since)"
    r"\s+(?:the\s+)?"
    r"(?:following|next|last|past|first|second|same|subsequent)?\s*"
    r"(?:\d+\s+|couple\s+of\s+|few\s+|two\s+|three\s+|four\s+|five\s+|"
    r"six\s+|seven\s+|eight\s+|nine\s+|ten\s+|twelve\s+|eighteen\s+)?"
    r"(?:weeks?|months?|quarters?|years?|days?|sprints?|halves?|half|seasons?)"
    # fiscal periods, named outright
    r"|Q[1-4]\b|H[12]\b|FY\s?\d{2,4}"
    # a named month, with or without a year
    r"|(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b"
    # "last summer", "that winter", "in 2023"
    r"|(?:last|this|that|next)\s+(?:spring|summer|fall|autumn|winter)"
    r"|(?:19|20)\d{2}\b"
    r")", re.IGNORECASE)

_ATTRIBUTION = re.compile(
    r"\b(?:because|which caused|as a result|attributed|measured by|"
    r"we verified|confirmed by|A/B|control group|held constant|isolated|"
    r"ruled out|the only change)\b", re.IGNORECASE)

_ALTERNATIVE = re.compile(
    r"\b(?:instead of|rather than|we considered|the alternative|we also "
    r"looked at|we rejected|the other option|we could have|versus|"
    r"as opposed to|weighed)\b", re.IGNORECASE)

# TRADEOFF, THE SECOND VOCABULARY DEFECT OF THE SAME SHAPE.
# This was a fixed list of business-school phrases -- "trade-off", "at the
# cost of", "in exchange", "downside", "sacrificed", "compromise". A driver
# describing the clearest tradeoff in his interview said:
#
#   "I shut down at a truck stop and called dispatch before they called me.
#    We lost the appointment and the receiver charged us a redelivery.
#    I would do it again."
#
# A cost paid on purpose, stated plainly, with the reasoning attached -- and
# not one word of it matched. The competency then reported that no alternative
# had been weighed, which is the opposite of what he said.
#
# So the explicit phrases stay, and a STRUCTURAL path is added beside them: a
# cost that was incurred, plus a marker that it was chosen rather than
# suffered. Both are required, because "we lost the appointment" alone is a
# bad outcome and not a decision.
_TRADEOFF_EXPLICIT = re.compile(
    r"\b(?:trade[- ]?off|at the cost of|in exchange|downside|the catch|"
    r"we gave up|sacrific\w+|compromise)\b", re.IGNORECASE)

#: Something was given up.
_COST_INCURRED = re.compile(
    r"\b(?:lost|losing|cost (?:us|me|them|the)|charged (?:us|me|them)|"
    r"ate (?:the|a)|absorb\w*|missed|paid for|took the (?:hit|loss)|"
    r"wrote off|at a loss|gave up|out of pocket|"
    r"went late|delivered late|had to eat)\b", re.IGNORECASE)

#: It was chosen, not suffered.
_DELIBERATE = re.compile(
    r"(?:\bi'?(?:d| would) do (?:it|that) again\b|\brather than\b|"
    r"\binstead of\b|\bi chose\b|\bi decided\b|\bit was worth\b|"
    r"\bworth it\b|\bbetter than\b|\bi'?d rather\b|\bevery time\b|"
    r"\bon purpose\b|\bdeliberately\b|\bmade the call\b)", re.IGNORECASE)


def _has_tradeoff(text: str) -> bool:
    if _TRADEOFF_EXPLICIT.search(text):
        return True
    return bool(_COST_INCURRED.search(text) and _DELIBERATE.search(text))

_FAILURE = re.compile(
    r"\b(?:did ?n[o']t work|failed|mistake|wrong|regret|would do "
    r"differently|in hindsight|backfired|broke|rolled back|had to redo|"
    r"got it wrong|underestimated)\b", re.IGNORECASE)

_CONFLICT = re.compile(
    r"\b(?:disagreed|pushed back|conflict|argument|tension|escalated|"
    r"difficult conversation|refused|stood my ground|convinced)\b",
    re.IGNORECASE)

#: Named specifics: proper nouns, systems, tools. A crude but honest proxy for
#: "this person is describing a particular thing rather than a category".
_PROPER = re.compile(r"\b[A-Z][a-zA-Z0-9]{2,}(?:\s+[A-Z][a-zA-Z0-9]+)?\b")

_GENERIC_OPENER = re.compile(
    r"^\s*(?:i (?:always|generally|usually|typically|like to|try to|believe|"
    r"think it'?s important)|my approach is|the way i|it depends|"
    r"generally speaking|in general)\b", re.IGNORECASE)

_NON_ANSWERS = {"skip", "pass", "next", "none", "nothing", "no", "n/a", "na",
                "idk", "i don't know", "i dont know", "dunno", "not sure",
                "can't say", "cant say", "prefer not to answer"}


@dataclass
class AnswerAnalysis:
    """What one answer established, and what it left open."""

    # substance
    is_substantive: bool
    non_answer_kind: Optional[str] = None
    word_count: int = 0

    # what the answer contains
    has_first_person_action: bool = False
    team_voice_only: bool = False
    named_specifics: int = 0
    is_generic_approach: bool = False

    # quantitative support
    has_number: bool = False
    #: A number offered as a RESULT, as opposed to a descriptive quantity.
    has_outcome_number: bool = False
    #: How many DIFFERENT quantities the answer contains. An operations answer
    #: carries its specifics as numbers rather than as names.
    distinct_numbers: int = 0
    has_baseline: bool = False
    has_timeframe: bool = False
    has_attribution: bool = False

    # reasoning
    has_alternative: bool = False
    has_tradeoff: bool = False
    has_failure_reflection: bool = False
    has_conflict_account: bool = False

    # relation to what came before
    contradicts: List[str] = field(default_factory=list)

    #: What a follow-up should go after, most valuable first.
    gaps: List[str] = field(default_factory=list)
    analysis_version: str = ANALYSIS_VERSION

    @property
    def is_specific(self) -> bool:
        """Is this about a particular thing rather than a general practice?

        THE WORD FLOOR IS NOT A MEASURE OF SUBSTANCE.
        A flat `word_count >= 25` marked this as not specific:

            "Six years on reefer, mostly a Kenworth T680. McAllen up to
             Chicago about three times a month for four of those years."

        Twenty-two words, four named specifics, three numbers, and the most
        concrete answer in the interview. It was probed for "one concrete,
        named example" and the competency finished UNCOVERED. That penalises
        every candidate who answers tersely, which in trucking is most of
        them.

        So the floor now only applies to the WEAK case -- a single specific
        and nothing else, where "yeah, at Walmart" and a real answer look
        alike. Two or more named specifics, or one plus a number, is specific
        at any length.
        """
        if self.is_generic_approach:
            return False
        strongly_named = (self.named_specifics >= 2
                          or (self.named_specifics >= 1 and self.has_number))
        # DENSE NUMBERS ARE SPECIFICS TOO.
        # "60 to 80 loads a week, 40 trucks, empty miles from 22% to 18%
        # between Q2 and Q4" contains no proper noun at all -- an operations
        # answer is measured in numbers, not names -- and was therefore held
        # to the 25-word floor and failed it at sixteen. Three or more
        # distinct quantities is a specific answer in any domain.
        strongly_numeric = self.distinct_numbers >= 3
        if strongly_named or strongly_numeric:
            return True
        return ((self.named_specifics >= 1 or self.has_number)
                and self.word_count >= 25)

    @property
    def ownership_is_clear(self) -> bool:
        return self.has_first_person_action and not self.team_voice_only

    @property
    def quantitative_claim_is_supported(self) -> bool:
        """A RESULT without a baseline or a period is not yet a measurement.

        A descriptive quantity needs none of that: "42,000 pounds of lettuce"
        is not a claim about performance and asking for its baseline is a
        category error.
        """
        if not self.has_outcome_number:
            return True
        return self.has_baseline and (self.has_timeframe or self.has_attribution)


def _detect_contradictions(answer: str,
                           prior_claims: Sequence[C.Claim]) -> List[str]:
    """Numeric disagreement between an answer and a resume claim.

    Only NUMERIC, and only where the answer is talking about the same subject.
    Anything looser produces false accusations, and the cost of a false
    contradiction -- putting it to a candidate that their resume is wrong -- is
    far higher than the cost of missing one.
    """
    out: List[str] = []
    low = answer.lower()

    for claim in prior_claims:
        if claim.quantity_value is None or not claim.subject:
            continue
        subject_words = [w for w in re.findall(r"[a-z]{4,}", claim.subject.lower())]
        if not subject_words or not any(w in low for w in subject_words):
            continue

        # THE NUMBER IN THE ANSWER MUST CARRY THE SAME UNIT.
        #
        # Without this the detector compared a TENURE claim against every bare
        # number in the answer. A dispatcher whose resume said "4 years at a
        # 40-truck regional carrier", answering "empty miles from about 22%
        # down to 18%", was told to his face:
        #
        #     "resume says 4years for truck regional carrier;
        #      the answer says 22"
        #
        # Four years against twenty-two percent. A false contradiction is the
        # most expensive error this module can make -- it puts to a candidate
        # that their resume is wrong, on camera, in a recording a recruiter
        # will later watch -- so the comparison is now unit-for-unit and a
        # claim whose unit cannot be matched in the answer is simply not
        # compared.
        unit = (claim.quantity_unit or "").lower()
        found = _numbers_in_unit(low, unit)
        if not found:
            continue

        target = float(claim.quantity_value)
        # A restatement within 10% is the same claim told loosely.
        if any(abs(f - target) <= max(0.1 * target, 0.5) for f in found):
            continue
        # Only flag when a number of the same ORDER is present -- otherwise
        # "12 engineers" vs "3 direct reports" and an unrelated "2019" both
        # look like disagreement.
        near = [f for f in found if 0 < f and (f / target if target else 0) < 10]
        if near:
            # QUOTE THE RESUME, DO NOT DESCRIBE IT.
            # `subject` is an extractor artifact -- "reduced", "drivers" --
            # and "your resume says 18% for reduced" is not a sentence anyone
            # would say. The line the candidate actually wrote is both more
            # accurate and easier for them to answer.
            line = " ".join((claim.source_excerpt or "").split())
            if len(line) > 110:
                line = line[:110].rsplit(" ", 1)[0] + "…"
            where = f'"{line}"' if line else str(claim.subject)
            out.append(
                f"I have {where} on your resume, and I heard "
                f"{_amount(near[0], unit)}")
    return out


#: How each unit is written in an answer. A tenure claim is only contradicted
#: by another duration; a headcount only by another count of the same thing.
_UNIT_SUFFIX = {
    "%": r"\s*(?:%|percent)",
    "years": r"\s*(?:years?|yrs?)",
    "months": r"\s*months?",
    "USD": None,          # handled by the $ prefix below
}


def _numbers_in_unit(low: str, unit: str) -> List[float]:
    """Every number in the answer that is expressed in `unit`.

    Unit casing is normalised because callers differ: the extractor stores
    "USD" and "%", and `verification` had lowercased its copy before calling
    in. That mismatch silently sent every dollar claim down the counted-noun
    path, where it matched nothing, and a $120,000 answer to a $50,000 claim
    came back as INSUFFICIENT_EVIDENCE instead of a contradiction.
    """
    unit = (unit or "").strip()
    if unit.upper() == "USD":
        return [float(m.replace(",", ""))
                for m in re.findall(r"\$\s*(\d[\d,]*(?:\.\d+)?)", low)]

    suffix = _UNIT_SUFFIX.get(unit, _UNIT_SUFFIX.get(unit.lower()))
    if suffix is None:
        # A counted noun: "12 drivers", "40 trucks". The unit IS the noun, so
        # require it (singular or plural) right after the number.
        noun = re.escape(unit.rstrip("s"))
        if not noun:
            return []
        suffix = rf"\s*{noun}s?\b"

    return [float(m.replace(",", ""))
            for m in re.findall(rf"\b(\d[\d,]*(?:\.\d+)?){suffix}", low)]


def _amount(value: float, unit: str) -> str:
    """A quantity written the way it would be said out loud."""
    unit = (unit or "").strip()
    if unit == "%":
        return f"{value:g}%"
    if unit.upper() == "USD":
        return f"${value:,.0f}"
    if not unit:
        return f"{value:g}"
    noun = unit if value != 1 else unit.rstrip("s")
    return f"{value:g} {noun}"


def analyse(answer_text: str, *,
            prior_claims: Sequence[C.Claim] = (),
            expects_metric: bool = False,
            expects_ownership: bool = False,
            expects_tradeoff: bool = False) -> AnswerAnalysis:
    """Analyse one answer.

    The `expects_*` flags come from the competency being probed, so the gaps
    reported are the ones that matter HERE. A missing tradeoff is a gap when
    assessing design judgement and noise when assessing equipment experience.
    """
    text = (answer_text or "").strip()
    words = text.split()
    stripped = text.lower().strip(" .!?,")

    if not text or stripped in _NON_ANSWERS or len(words) < 4:
        kind = ("SKIPPED" if stripped in ("skip", "pass", "next")
                else "REFUSED" if stripped in ("no", "prefer not to answer")
                else "TOO_SHORT")
        return AnswerAnalysis(is_substantive=False, non_answer_kind=kind,
                              word_count=len(words),
                              gaps=["the question was not answered"])

    a = AnswerAnalysis(
        is_substantive=True,
        word_count=len(words),
        has_first_person_action=bool(_FIRST_PERSON_ACTIVE.search(text)),
        named_specifics=len(set(_PROPER.findall(text))),
        is_generic_approach=bool(_GENERIC_OPENER.search(text)),
        has_number=bool(_NUMBER.search(text)),
        distinct_numbers=len({m.group(0).strip()
                              for m in _BARE_QUANTITY.finditer(text)}),
        has_outcome_number=bool(_OUTCOME_NUMBER.search(text)),
        has_baseline=bool(_BASELINE.search(text)),
        has_timeframe=bool(_TIMEFRAME.search(text)),
        has_attribution=bool(_ATTRIBUTION.search(text)),
        has_alternative=bool(_ALTERNATIVE.search(text)),
        has_tradeoff=_has_tradeoff(text),
        has_failure_reflection=bool(_FAILURE.search(text)),
        has_conflict_account=bool(_CONFLICT.search(text)),
    )
    a.team_voice_only = (bool(_TEAM_VOICE.search(text))
                         and not a.has_first_person_action)
    a.contradicts = _detect_contradictions(text, prior_claims)

    # --- gaps, most valuable first ----------------------------------------
    gaps: List[str] = []
    if a.contradicts:
        gaps.append("clarify an apparent disagreement with the resume")

    # Ordering matters: the FIRST gap becomes the next question. When the
    # competency being assessed is ownership and the answer is in team voice,
    # "what did you personally do" is worth more than "give me an example" --
    # asking for another example first would likely get another team story.
    ownership_gap = ((expects_ownership or a.team_voice_only)
                     and not a.ownership_is_clear)
    if ownership_gap and expects_ownership:
        gaps.append("separate what the candidate did from what the team did")
    if not a.is_specific:
        gaps.append("get one concrete, named example")
    if ownership_gap and not expects_ownership:
        gaps.append("separate what the candidate did from what the team did")
    # Only a number presented as a RESULT needs a baseline. "42,000 pounds of
    # lettuce" and "38 degrees" are descriptive facts about the load, not
    # performance claims, and demanding a baseline for them turned a precise,
    # concrete answer into three probes and an UNSUPPORTED_METRIC finding.
    if a.has_outcome_number and not a.has_baseline:
        gaps.append("establish the baseline the number is measured against")
    if a.has_outcome_number and not a.has_timeframe:
        gaps.append("establish the time period")
    if a.has_outcome_number and not a.has_attribution:
        gaps.append("establish how the result was attributed to this change")
    if expects_metric and not a.has_outcome_number:
        gaps.append("get a number, or establish that none exists")
    if expects_tradeoff and not (a.has_alternative or a.has_tradeoff):
        gaps.append("get the alternative that was considered and rejected")
    if not a.has_failure_reflection and a.is_specific:
        gaps.append("probe a limit, failure or thing they would change")

    a.gaps = gaps
    return a
