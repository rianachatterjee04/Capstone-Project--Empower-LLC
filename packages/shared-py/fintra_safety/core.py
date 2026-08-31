"""
fintra_safety.core — the deterministic safety primitives.

Pure Python, zero network, zero heavy deps (only `re` + `dataclasses`). Everything
here is a pure function of its input so it can run inline on any AI surface without
adding latency or a failure mode of its own. Callers still wrap invocations in
try/except (a safety layer must never break an AI response), but the functions below
are themselves defensive: they coerce bad input and never raise on ordinary strings.

Two jobs:

  1. INPUT SCREENING — `screen_input()` looks for self-harm / suicide *intent* in the
     user's message. This is a compassionate safety net, NOT a content filter: it is
     tuned for precision (few false positives) because this is a B2B finance/workforce
     product where "kill the process", "financial suicide", or a medical-coding query
     must NOT be mistaken for a crisis.

  2. OUTPUT ANNOTATION — `annotate_output()` appends a concise, non-alarming disclaimer
     when AI output touches a regulated advice domain (tax / legal / investment) or is
     advice-like in a softer domain (financial / accounting). Idempotent via a
     zero-width sentinel so the same text is never double-stamped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

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


# ──────────────────────────────────────────────────────────────────────────────
#  Public value types
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class InputVerdict:
    """Result of screening a user's input.

    crisis        — True when self-harm / suicide intent was detected.
    category      — a short machine label (e.g. "self_harm") or None.
    safe_response — a ready-to-send compassionate message when crisis is True, else None.
    """
    crisis: bool
    category: Optional[str] = None
    safe_response: Optional[str] = None


@dataclass(frozen=True)
class GuardedResult:
    """Result of `guard_completion` — the text to actually return, plus what happened.

    text     — the final text (safe_response if a crisis replaced it, else the
               disclaimer-annotated completion).
    replaced — True when the original completion was replaced by the crisis response.
    crisis   — True when the user input was flagged as a crisis.
    """
    text: str
    replaced: bool
    crisis: bool


# Zero-width sentinel appended inside every disclaimer block. Invisible in both
# plain-text and rendered-markdown surfaces, and vanishingly unlikely to occur in
# natural text, so `SAFE_DISCLAIMER_MARKER in text` is a reliable "already stamped"
# test that keeps annotate_output idempotent across the whole pipeline.
SAFE_DISCLAIMER_MARKER = "​⁠​"

# The five advice domains this module knows how to disclaim.
DOMAINS = ("tax", "legal", "accounting", "financial", "investment")


# ──────────────────────────────────────────────────────────────────────────────
#  Crisis / self-harm screening
# ──────────────────────────────────────────────────────────────────────────────
#
# Design for PRECISION. We match self-directed *intent* phrases, never the bare word
# "kill" or "suicide" — so "kill this process", "kill the job", and the common finance
# idiom "financial/career suicide" are NOT flagged. A few phrase families carry a
# follower-guard to reject benign continuations (e.g. "end my life insurance",
# "no reason to live *in* Denver"), and the clinical suffix family (suicidal ideation)
# is suppressed when explicit medical-coding context is present so the Medical/Dental
# verticals can ask coding questions without tripping the net.

# Always a crisis — self-directed by construction (myself / my own life / die wish).
_ALWAYS = re.compile(
    r"\b("
    r"kill(?:ing)? myself|kill my self|"
    r"hurt(?:ing)? myself|harm(?:ing)? myself|hurt my self|harm my self|"
    r"cut(?:ting)? myself|"
    r"self ?-? ?harm|"
    r"want(?:ing)? to die|wanna die|want to be dead|"
    r"better off dead|"
    r"wish i (?:was|were) dead|"
    r"want to end it all|ready to end it all|just want to end it all|"
    r"don'?t want to live anymore|do not want to live anymore|"
    r"don'?t want to live any longer|do not want to live any longer"
    r")\b"
)

# "…my life" family — reject the insurance/savings/policy compounds.
_LIFE = re.compile(r"\b(end(?:ing)? my (?:own )?life|take my own life|taking my own life)\b")
_LIFE_BENIGN = frozenset({
    "insurance", "insurances", "savings", "policy", "policies",
    "cover", "coverage", "plan", "plans", "cycle", "cycles",
})

# "…to live / to be alive" family — reject "live *in/at/here…*" location phrasings.
_ALIVE = re.compile(
    r"\b(don'?t want to be alive|do not want to be alive|"
    r"no reason to (?:live|be alive)|nothing to live for)\b"
)
_ALIVE_BENIGN = frozenset({
    "in", "at", "on", "near", "here", "there", "abroad", "alone",
    "downtown", "close", "overseas", "with", "by", "together",
})

# Suicide-term family — suppressed under explicit medical-coding context.
_SUICIDE = re.compile(
    r"\b("
    r"i'?m suicidal|i am suicidal|feeling suicidal|feel suicidal|"
    r"so suicidal|really suicidal|very suicidal|"
    r"suicidal thoughts|suicidal ideation|"
    r"commit(?:ting)? suicide|attempt(?:ing|ed)? suicide|"
    r"thinking (?:about|of) suicide|thoughts of suicide|"
    r"considering suicide|contemplating suicide|planning to commit suicide"
    r")\b"
)

# Presence of any of these means the message is almost certainly clinical/billing
# context (Medical/Dental verticals), so the suicide-TERM family is treated as data,
# not a personal disclosure. First-person self-harm phrases above are NEVER suppressed.
_CLINICAL = re.compile(
    r"\b(icd(?:-? ?10)?|cpt|hcpcs|diagnosis code|billing code|denial code|"
    r"code for|claim for|claim denial|reimbursement|superbill)\b"
)

_FOLLOWER = re.compile(r"\s+([a-z']+)")

_CRISIS_CATEGORY = "self_harm"


def _normalize(text: str) -> str:
    """Lowercase, straighten curly apostrophes, and collapse whitespace."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    text = text.replace("’", "'").replace("ʼ", "'")
    return re.sub(r"\s+", " ", text).strip().lower()


def _survives(text: str, end: int, benign: frozenset) -> bool:
    """True unless the word immediately following a match is a benign continuation."""
    if not benign:
        return True
    m = _FOLLOWER.match(text, end)
    if not m:
        return True
    return m.group(1) not in benign


def _any_match(pattern: re.Pattern, text: str, benign: frozenset = frozenset()) -> bool:
    """True if `pattern` matches `text` with at least one match surviving the follower guard."""
    for m in pattern.finditer(text):
        if _survives(text, m.end(), benign):
            return True
    return False


# The compassionate crisis response. Proportional for a B2B finance/workforce tool:
# it expresses care, points to emergency services + the US 988 Lifeline (call/text) and
# international resources, and is explicit that Fintra is a business tool, not a crisis
# service. It does not attempt counseling.
CRISIS_SAFE_RESPONSE = (
    "I'm really sorry you're feeling this way, and I'm genuinely concerned about your "
    "safety. I'm Fintra, a business finance tool — not a crisis service — so I can't give "
    "you the support you deserve here, but please reach out right now to someone who can:\n\n"
    "- If you're in immediate danger, call your local emergency number (911 in the US).\n"
    "- In the US, call or text **988** to reach the Suicide & Crisis Lifeline, free and "
    "available 24/7.\n"
    "- Outside the US, contact your local emergency services or a crisis line in your "
    "country — findahelpline.com lists options worldwide.\n\n"
    "You don't have to get through this alone. Please talk to someone who can help right now."
)


def screen_input(text: str) -> InputVerdict:
    """Screen a user's input for self-harm / suicide intent.

    Returns an InputVerdict. When `crisis` is True, `safe_response` carries a
    compassionate message to return in place of a normal AI answer. Deterministic,
    defensive (never raises on ordinary input), and tuned for precision.
    """
    try:
        norm = _normalize(text)
        if not norm:
            return InputVerdict(crisis=False)

        crisis = (
            _any_match(_ALWAYS, norm)
            or _any_match(_LIFE, norm, _LIFE_BENIGN)
            or _any_match(_ALIVE, norm, _ALIVE_BENIGN)
        )
        if not crisis and not _CLINICAL.search(norm):
            crisis = _any_match(_SUICIDE, norm)

        if crisis:
            return InputVerdict(
                crisis=True,
                category=_CRISIS_CATEGORY,
                safe_response=CRISIS_SAFE_RESPONSE,
            )
        return InputVerdict(crisis=False)
    except Exception:
        # A screening failure must never block the pipeline. Fail OPEN (no crisis)
        # so the normal answer path continues; the caller stays responsible for the
        # response either way.
        return InputVerdict(crisis=False)


# ──────────────────────────────────────────────────────────────────────────────
#  Output disclaimer annotation
# ──────────────────────────────────────────────────────────────────────────────
_DOMAIN_NOTES = {
    "tax": (
        "This is general information generated by AI, not professional tax advice — "
        "confirm with a licensed tax professional before you act on it."
    ),
    "legal": (
        "This is general information generated by AI, not legal advice — confirm with "
        "a licensed attorney before you act on it."
    ),
    "accounting": (
        "This is general information generated by AI, not professional accounting or "
        "audit advice — confirm the treatment with a licensed accountant."
    ),
    "financial": (
        "This is general information generated by AI, not personalized financial advice."
    ),
    "investment": (
        "This is general information generated by AI and is not investment advice — "
        "Fintra is not a registered investment adviser."
    ),
}

# Regulated domains: a disclaimer is warranted on keyword presence alone (stating tax
# or legal information carries a duty regardless of whether it is framed as advice).
_REGULATED = frozenset({"tax", "legal", "investment"})
# Softer domains: only disclaim when the text is actually advice-like, so routine
# bookkeeping / reporting answers are not stamped on every reply.
_SOFT = frozenset({"financial", "accounting"})

_DOMAIN_PATTERNS = {
    "tax": re.compile(
        r"\b(tax(?:es|able|ation)?|irs|deduction|deductible|"
        r"withhold(?:ing|ings)?|1099|w-?2|vat|capital gains|tax return|"
        r"estimated taxes|write-?off)\b"
    ),
    "legal": re.compile(
        r"\b(legal advice|lawsuits?|attorneys?|lawyers?|litigation|statutes?|"
        r"legally binding|breach of contract|intellectual property|copyright|"
        r"trademark|non-?compete|nda)\b"
    ),
    "investment": re.compile(
        r"\b(invest(?:s|ing|ment|ments|or|ors)?|securities|mutual funds?|brokerage|"
        r"etfs?|401\(?k\)?|roth ira|ira|cryptocurrenc(?:y|ies)|equit(?:y|ies)|"
        r"stock market|bond market)\b"
    ),
    "financial": re.compile(
        r"\b(financial (?:advice|plan|planning|planner)|personal finance|net worth|"
        r"retirement (?:savings|planning|plan)|refinanc(?:e|ing)|financial future|"
        r"money management|manage your money|save for retirement)\b"
    ),
    "accounting": re.compile(
        r"\b(accounting treatment|revenue recognition|gaap|ifrs|"
        r"capitaliz(?:e|ing|ation)|amortiz(?:e|ing|ation)|depreciat(?:e|ion)|"
        r"how (?:should|do) (?:i|you) record|audit opinion)\b"
    ),
}

_ADVICE_RE = re.compile(
    r"\b(you should|you need to|you'?ll want to|i recommend|i'?d recommend|"
    r"i would recommend|we recommend|my recommendation|recommended next steps|"
    r"i suggest|i'?d suggest|you could consider|you might consider|you may want to|"
    r"it'?s advisable|it is advisable|best to|you ought to|i advise|my advice|"
    r"make sure to|be sure to|recommended)\b"
)


def _is_advice_like(norm: str) -> bool:
    return bool(_ADVICE_RE.search(norm))


def _detect_domains(norm: str) -> List[str]:
    """Auto-detect which advice domains the text touches, in stable display order."""
    advice = _is_advice_like(norm)
    found: List[str] = []
    for domain in DOMAINS:  # DOMAINS is already the display order
        if not _DOMAIN_PATTERNS[domain].search(norm):
            continue
        if domain in _SOFT and not advice:
            continue
        found.append(domain)
    return found


def has_disclaimer(text: str) -> bool:
    """True if the text already carries a fintra_safety disclaimer marker."""
    return isinstance(text, str) and SAFE_DISCLAIMER_MARKER in text


def _clean_domains(domains: Optional[Sequence[str]]) -> List[str]:
    """Normalize + validate an explicit domains list into stable display order."""
    if not domains:
        return []
    wanted = {str(d).strip().lower() for d in domains}
    return [d for d in DOMAINS if d in wanted]


def annotate_output(text: str, *, domains: Optional[Sequence[str]] = None) -> str:
    """Append the right advice disclaimer(s) to AI output.

    - If `domains` is given, those (validated) domains are disclaimed directly.
    - Otherwise the domain(s) are auto-detected from the text: regulated domains
      (tax/legal/investment) on keyword presence, softer domains (financial/accounting)
      only when the text is advice-like.
    Idempotent — a text that already carries SAFE_DISCLAIMER_MARKER is returned
    unchanged. Defensive: never raises on ordinary input.
    """
    try:
        if not isinstance(text, str) or not text.strip():
            return text if isinstance(text, str) else ("" if text is None else str(text))
        if has_disclaimer(text):
            return text

        selected = _clean_domains(domains) if domains else _detect_domains(_normalize(text))
        if not selected:
            return text

        notes = [_DOMAIN_NOTES[d] for d in selected if d in _DOMAIN_NOTES]
        if not notes:
            return text

        block = "\n\n---\n" + "  \n".join(f"_{n}_" for n in notes) + SAFE_DISCLAIMER_MARKER
        return text + block
    except Exception:
        # Never let annotation break the response — return the original text.
        return text if isinstance(text, str) else str(text)


# ──────────────────────────────────────────────────────────────────────────────
#  Convenience combiner + helper notes
# ──────────────────────────────────────────────────────────────────────────────
def guard_completion(
    user_input: str,
    completion_text: str,
    domains: Optional[Sequence[str]] = None,
) -> GuardedResult:
    """Screen the input and annotate the output in one call.

    If the input is a crisis, the completion is REPLACED by the compassionate safe
    response (replaced=True, crisis=True). Otherwise the completion is annotated with
    any applicable advice disclaimers (replaced=False, crisis=False). Fully defensive.
    """
    try:
        verdict = screen_input(user_input or "")
        if verdict.crisis and verdict.safe_response:
            return GuardedResult(text=verdict.safe_response, replaced=True, crisis=True)
    except Exception:
        pass  # fall through to plain annotation on any screening error

    safe_text = completion_text if isinstance(completion_text, str) else (
        "" if completion_text is None else str(completion_text)
    )
    try:
        safe_text = annotate_output(safe_text, domains=domains)
    except Exception:
        pass
    return GuardedResult(text=safe_text, replaced=False, crisis=False)


def uncertainty_note() -> str:
    """A concise, reusable 'this may be wrong — verify' note for uncertain output."""
    return (
        "Note: AI-generated and may be incomplete or contain errors — please verify "
        "important details before relying on this."
    )


def not_verified_evidence_note() -> str:
    """A note for answers composed from data that hasn't been checked against source evidence."""
    return (
        "This was generated from available data and has not been independently verified "
        "against source evidence."
    )
