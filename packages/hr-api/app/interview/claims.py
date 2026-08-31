"""Extract structured claims from candidate materials, with their sources.

THE RULE THIS MODULE EXISTS TO ENFORCE
A claim is something the candidate said. Every extracted claim carries the
document it came from and the character span within it, and `source_excerpt`
holds the candidate's own words verbatim. Nothing downstream may probe, cite or
score a claim that cannot point back at text.

That is not bookkeeping. The interviewer asks questions like "your resume says
you cut settlement failures by 40%" -- and if the resume did not say that, the
product has invented an accusation and put it to a candidate under pressure.
The span is what makes that impossible.

DETERMINISTIC FIRST, LLM SECOND
The deterministic extractor runs always. It finds what patterns can find:
quantified outcomes, equipment, certifications, tenure, tooling. It is boring
and it cannot hallucinate, because every claim it emits is a span of the
source.

An LLM pass may add claims the patterns miss, and those are stored with
`is_inference = true` and a confidence. The schema will not accept an inference
without one. Downstream, an inferred claim is usable as a HOOK for a question
but never as an established fact -- see `Claim.may_be_asserted`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence

# Claim types, mirroring candidate_claims.claim_type.
SKILL = "SKILL"
PROJECT = "PROJECT"
RESPONSIBILITY = "RESPONSIBILITY"
LEADERSHIP = "LEADERSHIP"
MEASURABLE_OUTCOME = "MEASURABLE_OUTCOME"
DOMAIN_EXPERIENCE = "DOMAIN_EXPERIENCE"
CERTIFICATION = "CERTIFICATION"
ROLE_HISTORY = "ROLE_HISTORY"
TECHNICAL_CAPABILITY = "TECHNICAL_CAPABILITY"
CAREER_TRANSITION = "CAREER_TRANSITION"
EQUIPMENT_OPERATED = "EQUIPMENT_OPERATED"
OTHER = "OTHER"

RESUME = "RESUME"
APPLICATION = "APPLICATION"
PORTFOLIO = "PORTFOLIO"
RECRUITER_NOTE = "RECRUITER_NOTE"
JOB_DESCRIPTION = "JOB_DESCRIPTION"

EXTRACTOR_VERSION = "claims-2026.08.29"


@dataclass
class Claim:
    """One thing the candidate asserted, and where they asserted it."""

    claim_type: str
    claim_text: str
    source_kind: str
    source_ref: str
    source_excerpt: str
    source_span_start: Optional[int] = None
    source_span_end: Optional[int] = None

    subject: Optional[str] = None
    quantity_value: Optional[float] = None
    quantity_unit: Optional[str] = None
    time_period: Optional[str] = None

    is_inference: bool = False
    confidence: Optional[float] = None
    extractor: str = EXTRACTOR_VERSION
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    extracted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    @property
    def may_be_asserted(self) -> bool:
        """Whether this claim can be stated back to the candidate as fact.

        An inference may open a question ("it looks like you worked on X --
        is that right?") but must never be put as a quotation of them.
        """
        return not self.is_inference

    @property
    def is_quantified(self) -> bool:
        return self.quantity_value is not None

    def as_row(self) -> dict:
        return {
            "claim_type": self.claim_type,
            "claim_text": self.claim_text,
            "subject": self.subject,
            "quantity_value": self.quantity_value,
            "quantity_unit": self.quantity_unit,
            "time_period": self.time_period,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "source_span_start": self.source_span_start,
            "source_span_end": self.source_span_end,
            "source_excerpt": self.source_excerpt,
            "is_inference": self.is_inference,
            "confidence": self.confidence,
            "extractor": self.extractor,
            "model_name": self.model_name,
            "model_version": self.model_version,
        }


# ---------------------------------------------------------------------------
# Deterministic patterns
# ---------------------------------------------------------------------------

_SENTENCE = re.compile(r"[^.\n;•]+")

# A percentage or multiple attached to a verb of change. This is the highest
# value claim type: it is specific, checkable, and the thing candidates most
# often cannot substantiate.
_OUTCOME = re.compile(
    r"\b(reduc\w+|cut|decreas\w+|lower\w+|improv\w+|increas\w+|grew|grow\w+|"
    r"rais\w+|sav\w+|boost\w+|accelerat\w+|shorten\w+)\b[^.\n]{0,80}?"
    r"(\d+(?:\.\d+)?)\s*(%|percent|x|bps|hours?|days?|weeks?|months?|"
    r"seconds?|ms|minutes?)",
    re.IGNORECASE)

# Money outcomes, which the percentage pattern misses.
_MONEY = re.compile(
    r"\b(reduc\w+|cut|sav\w+|generat\w+|deliver\w+|clos\w+|bill\w+|grew)\b"
    r"[^.\n]{0,60}?\$\s?(\d[\d,]*(?:\.\d+)?)\s*([kmb]|million|billion|thousand)?",
    re.IGNORECASE)

_TEAM_SIZE = re.compile(
    r"\b(?:managed|led|supervis\w+|oversaw|ran|headed)\b[^.\n]{0,40}?"
    r"\b(?:team of |group of |staff of )?(\d{1,4})\b[^.\n]{0,20}?"
    r"\b(engineers?|people|reports?|staff|drivers?|employees?|analysts?|"
    r"developers?|members?|technicians?)\b",
    re.IGNORECASE)

# TENURE.
# The gap between "N years" and the subject used to be `[^.\n]{0,40}?`, which
# let the subject start anywhere. "4 years at a 40-truck regional carrier"
# produced the subject "truck regional carrier", and the planner read that back
# to the candidate as "You put 4 years in truck regional carrier." A question
# built from a mangled phrase is worse than a generic one: it tells the
# candidate the system is quoting them without understanding them.
#
# So the gap is now made of named parts -- a connector, a determiner, a
# numeric compound -- and the subject itself is whole words only.
_TENURE = re.compile(
    r"\b(\d{1,2})(?:\+)?\s*(?:years?|yrs?)\b"
    r"(?:\s+(?:of|in|as|at|with|doing|driving|running))?"
    r"(?:\s+(?:an?|the))?"
    r"(?:\s+\d+[\w-]*)?"
    r"\s+((?:[A-Za-z][A-Za-z/&+'-]*)(?:\s+[A-Za-z][A-Za-z/&+'-]*){0,3}?)"
    r"(?=\s*(?:experience\b|exp\b|[.,;:\n]|$))",
    re.IGNORECASE)

#: Words that cannot start or end a subject read back to a candidate.
_SUBJECT_EDGE_NOISE = frozenset({
    "and", "or", "the", "a", "an", "at", "for", "of", "in", "on", "with",
    "to", "as", "by", "from", "experience", "exp", "work", "working"})


def readable_subject(raw: Optional[str]) -> Optional[str]:
    """A subject fit to be read back, or None.

    None is a real answer. When a phrase does not survive this, the caller
    falls back to quoting the resume line verbatim, which is always readable
    because the candidate wrote it.
    """
    s = " ".join((raw or "").split()).strip(" ,;:-/").lower()
    if not s:
        return None
    # "otr and regional" is a list, and a list does not read back as a noun
    # phrase. Take the first element.
    for sep in (" and ", " & ", " or ", ",", "/"):
        if sep in s:
            s = s.split(sep)[0].strip()
            break
    words = [w for w in s.split() if w]
    while words and words[0] in _SUBJECT_EDGE_NOISE:
        words.pop(0)
    while words and words[-1] in _SUBJECT_EDGE_NOISE:
        words.pop()
    if not words:
        return None
    out = " ".join(words[:4])
    return out if len(out) >= 3 else None

_CERTIFICATION = re.compile(
    r"\b(CDL[- ]?[ABC]?|TWIC|HAZMAT|Tanker endorsement|Doubles/Triples|"
    r"AWS Certified[\w \-]*|CPA|PMP|CISSP|Six Sigma[\w ]*|OSHA \d+|"
    r"Class [ABC] (?:CDL|license))\b",
    re.IGNORECASE)

# Trucking equipment. Ordered longest-first so "dry van" is not eaten by "van".
_EQUIPMENT = (
    "refrigerated", "reefer", "flatbed", "dry van", "step deck", "lowboy",
    "tanker", "hopper", "conestoga", "car hauler", "intermodal", "container",
    "doubles", "triples", "box truck", "straight truck", "sleeper", "day cab",
)

#: Same equipment, different word. Kept as one claim under the term a driver
#: would actually use, so two competencies cannot hook onto the same fact by
#: catching two spellings of it.
_EQUIPMENT_CANONICAL = {"refrigerated": "reefer", "straight truck": "box truck",
                        "over the road": "otr"}

_LANE_TYPE = ("otr", "over the road", "regional", "local", "dedicated",
              "long haul", "short haul", "last mile", "final mile")

_TECH = (
    "python", "typescript", "javascript", "java", "golang", "go", "rust",
    "c++", "postgres", "postgresql", "mysql", "redis", "kafka", "kubernetes",
    "docker", "terraform", "aws", "gcp", "azure", "react", "node", "django",
    "fastapi", "spark", "airflow", "snowflake", "dbt", "graphql",
)

_MULTIPLIER = {"k": 1_000, "thousand": 1_000, "m": 1_000_000,
               "million": 1_000_000, "b": 1_000_000_000, "billion": 1_000_000_000}


def _excerpt(text: str, start: int, end: int, pad: int = 0) -> tuple[str, int, int]:
    """The smallest sensible verbatim span around a match.

    Widened to sentence boundaries so the excerpt reads as something the
    candidate wrote rather than a fragment, because this string is quoted back
    to them in a question.
    """
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    # Walk out to sentence edges.
    while lo > 0 and text[lo - 1] not in ".\n;•":
        lo -= 1
    while hi < len(text) and text[hi] not in ".\n;•":
        hi += 1
    return text[lo:hi].strip(), lo, hi


def extract_deterministic(text: str, *, source_kind: str,
                          source_ref: str) -> List[Claim]:
    """Pattern-based extraction. Cannot hallucinate: every claim is a span."""
    if not text or not text.strip():
        return []

    claims: List[Claim] = []
    seen: set[tuple] = set()

    def add(c: Claim) -> None:
        key = (c.claim_type, c.claim_text.lower(), c.source_span_start)
        if key in seen:
            return
        seen.add(key)
        claims.append(c)

    # --- quantified outcomes ------------------------------------------------
    for m in _OUTCOME.finditer(text):
        excerpt, lo, hi = _excerpt(text, m.start(), m.end())
        value = float(m.group(2))
        unit = m.group(3).lower()
        add(Claim(
            claim_type=MEASURABLE_OUTCOME,
            claim_text=excerpt,
            subject=m.group(1).lower(),
            quantity_value=value,
            quantity_unit="%" if unit in ("%", "percent") else unit,
            source_kind=source_kind, source_ref=source_ref,
            source_excerpt=excerpt,
            source_span_start=lo, source_span_end=hi,
        ))

    for m in _MONEY.finditer(text):
        excerpt, lo, hi = _excerpt(text, m.start(), m.end())
        raw = float(m.group(2).replace(",", ""))
        suffix = (m.group(3) or "").lower()
        add(Claim(
            claim_type=MEASURABLE_OUTCOME,
            claim_text=excerpt,
            subject=m.group(1).lower(),
            quantity_value=raw * _MULTIPLIER.get(suffix, 1),
            quantity_unit="USD",
            source_kind=source_kind, source_ref=source_ref,
            source_excerpt=excerpt,
            source_span_start=lo, source_span_end=hi,
        ))

    # --- leadership / team size --------------------------------------------
    # Stored as a LEADERSHIP claim with the number kept structured, because
    # "managed 12" is the single most common claim that means two different
    # things. The verifier splits it later; the extractor must not.
    for m in _TEAM_SIZE.finditer(text):
        excerpt, lo, hi = _excerpt(text, m.start(), m.end())
        add(Claim(
            claim_type=LEADERSHIP,
            claim_text=excerpt,
            subject=m.group(2).lower(),
            quantity_value=float(m.group(1)),
            quantity_unit=m.group(2).lower(),
            source_kind=source_kind, source_ref=source_ref,
            source_excerpt=excerpt,
            source_span_start=lo, source_span_end=hi,
        ))

    # --- tenure / domain experience ----------------------------------------
    for m in _TENURE.finditer(text):
        domain = readable_subject(m.group(2))
        if not domain:
            continue
        excerpt, lo, hi = _excerpt(text, m.start(), m.end())
        add(Claim(
            claim_type=DOMAIN_EXPERIENCE,
            claim_text=excerpt,
            subject=domain,
            quantity_value=float(m.group(1)),
            quantity_unit="years",
            time_period=f"{m.group(1)} years",
            source_kind=source_kind, source_ref=source_ref,
            source_excerpt=excerpt,
            source_span_start=lo, source_span_end=hi,
        ))

    # --- certifications ------------------------------------------------------
    for m in _CERTIFICATION.finditer(text):
        excerpt, lo, hi = _excerpt(text, m.start(), m.end())
        add(Claim(
            claim_type=CERTIFICATION,
            claim_text=m.group(1),
            subject=m.group(1).lower(),
            source_kind=source_kind, source_ref=source_ref,
            source_excerpt=excerpt,
            source_span_start=lo, source_span_end=hi,
        ))

    # --- equipment / lanes / tech -------------------------------------------
    low = text.lower()
    for term, ctype in (
            *[(t, EQUIPMENT_OPERATED) for t in _EQUIPMENT],
            *[(t, DOMAIN_EXPERIENCE) for t in _LANE_TYPE],
            *[(t, TECHNICAL_CAPABILITY) for t in _TECH]):
        idx = low.find(term)
        if idx < 0:
            continue
        # Word boundary, so "go" does not match inside "goods".
        before_ok = idx == 0 or not low[idx - 1].isalnum()
        after = idx + len(term)
        after_ok = after >= len(low) or not low[after].isalnum()
        if not (before_ok and after_ok):
            continue
        excerpt, lo, hi = _excerpt(text, idx, after)
        canonical = _EQUIPMENT_CANONICAL.get(term, term)
        add(Claim(
            claim_type=ctype,
            claim_text=canonical,
            subject=canonical,
            source_kind=source_kind, source_ref=source_ref,
            source_excerpt=excerpt,
            source_span_start=lo, source_span_end=hi,
        ))

    return claims


def verify_spans(claims: Sequence[Claim], documents: dict[str, str]) -> List[str]:
    """Check every claim's span really contains its excerpt.

    Used as a control: an extractor that drifts -- or an LLM that returns a
    span it made up -- gets caught here rather than at the moment a candidate
    is asked about words they never wrote.

    Returns a list of human-readable problems; empty means every span holds.
    """
    problems: List[str] = []
    for c in claims:
        doc = documents.get(c.source_ref)
        if doc is None:
            problems.append(
                f"{c.claim_type} claim cites {c.source_ref!r}, which was not "
                f"among the documents supplied")
            continue
        if c.source_span_start is None or c.source_span_end is None:
            problems.append(
                f"{c.claim_type} claim {c.claim_text[:40]!r} has no span")
            continue
        actual = doc[c.source_span_start:c.source_span_end].strip()
        if actual != c.source_excerpt.strip():
            problems.append(
                f"{c.claim_type} claim span [{c.source_span_start}:"
                f"{c.source_span_end}] holds {actual[:50]!r} but the excerpt "
                f"says {c.source_excerpt[:50]!r}")
    return problems


def hooks_for(claims: Iterable[Claim], claim_types: Sequence[str],
              *, limit: int = 3) -> List[Claim]:
    """Pick the claims worth building a question around.

    Ranked by how much a probe would establish: a quantified outcome is the
    richest hook because it has a number to interrogate; a bare skill mention
    is the weakest because "you listed Python" is not a question.
    """
    wanted = [c for c in claims if c.claim_type in claim_types]

    # A bare tool or skill mention is the WEAKEST possible hook: "you listed
    # Python" is not a question, it is a prompt for the candidate to choose
    # what to talk about. A quantified outcome is the strongest: it has a
    # number, a baseline and an attribution to interrogate. Rank accordingly,
    # so a rich claim is never passed over for a keyword.
    _WEAK_HOOK_TYPES = (SKILL, TECHNICAL_CAPABILITY)

    # THE COMPETENCY'S OWN PREFERENCE ORDER COMES FIRST.
    # `claim_types` is written most-suitable-first by the rubric author:
    # equipment_experience asks for ("EQUIPMENT_OPERATED", "DOMAIN_EXPERIENCE",
    # ...) precisely because "you list reefer" is the right way into equipment
    # and "you put 6 years in regional" is not.
    #
    # That order used to be discarded here, and generic richness decided
    # instead. A quantified tenure claim outranked "reefer", so a driver whose
    # resume said reefer six times was asked about neither the equipment nor
    # the freight -- the competency was still covered, and covered by the wrong
    # question. Ranking now honours the rubric first and falls back to richness
    # to break ties within a type.
    preference = {t: i for i, t in enumerate(claim_types)}

    def rank(c: Claim) -> tuple:
        return (
            0 if c.claim_type in _WEAK_HOOK_TYPES else -1,   # weak sorts last
            preference.get(c.claim_type, len(preference)),
            0 if c.is_quantified else 1,
            0 if c.claim_type in (MEASURABLE_OUTCOME, LEADERSHIP, PROJECT) else 1,
            0 if not c.is_inference else 1,
            -len(c.source_excerpt or ""),
        )

    return sorted(wanted, key=rank)[:limit]
