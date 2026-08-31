"""AI Interview Service.

Generates structured interview questions for a job + candidate, scores the
candidate's free-text responses, and produces a defensible recommendation.

The service has two pluggable layers:

1. Question generation
   - "llm"   : uses app.services.llm.llm_complete when OPENAI_API_KEY is configured.
   - "local" : deterministic question bank tailored to detected skills + role.

2. Response scoring
   - Combines semantic similarity (resume + question + answer) with a small
     rubric of competency signals (clarity, specificity, ownership, depth).
   - Falls back to heuristic scoring if embeddings are unavailable.

The orchestration above is intentionally provider-agnostic so it works in a
demo with no external keys. When OPENAI_API_KEY is present the LLM path
upgrades automatically.
"""
from __future__ import annotations

import math
import re
import textwrap
from dataclasses import dataclass, field
from typing import Optional

from app.services.embeddings import embedding
from app.services.resume_matching_service import extract_skills

try:
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


# ---------------------------------------------------------------------------
# Question bank — competency areas covered for any role.
# ---------------------------------------------------------------------------
COMPETENCIES = [
    "role_fit",
    "technical_depth",
    "problem_solving",
    "communication",
    "ownership",
    "collaboration",
    "values_alignment",
]

GENERIC_QUESTIONS: dict[str, list[str]] = {
    "role_fit": [
        "Walk me through the project you are most proud of and why it mattered.",
        "What attracted you to this role and how does it connect to your career goals?",
    ],
    "technical_depth": [
        "Describe a technical decision you made recently and the trade-offs you weighed.",
        "Tell me about the most complex system you have built or contributed to.",
    ],
    "problem_solving": [
        "Tell me about a time you had to debug a difficult issue under pressure. Walk me through your approach.",
        "Describe a situation where you had to make a decision without enough information.",
    ],
    "communication": [
        "How do you explain a complex technical topic to a non-technical stakeholder? Give an example.",
        "Tell me about a time written communication changed an outcome for your team.",
    ],
    "ownership": [
        "Describe a time something went wrong that you owned end-to-end. What did you learn?",
        "What is a habit you have built to take responsibility for outcomes, not tasks?",
    ],
    "collaboration": [
        "Tell me about a disagreement with a teammate and how it was resolved.",
        "Describe a time you helped someone unblock without doing the work for them.",
    ],
    "values_alignment": [
        "What kind of environment helps you do your best work?",
        "Tell me about a feedback moment that shaped how you operate today.",
    ],
}

ROLE_SPECIFIC_HINTS: dict[str, list[str]] = {
    "engineer": [
        "Walk me through how you'd design a system to handle 10x current traffic.",
        "Explain a non-obvious bug you fixed and the root cause.",
    ],
    "manager": [
        "How do you set up a performance conversation when expectations are missed?",
        "Tell me about a hire you regret. What would you do differently?",
    ],
    "sales": [
        "Walk me through your most complex deal cycle from first call to close.",
        "How do you handle a champion who suddenly goes silent?",
    ],
    "hr": [
        "Describe a sensitive employee relations case you led to resolution.",
        "Tell me about a policy you changed and the business outcome.",
    ],
    "designer": [
        "Walk me through a design decision you reversed after user feedback.",
        "How do you balance speed vs. quality on a new feature exploration?",
    ],
    "data": [
        "Walk me through a model you shipped end-to-end — data, training, evaluation.",
        "Describe a time your analysis changed a leadership decision.",
    ],
}


@dataclass
class InterviewQuestion:
    id: str
    competency: str
    text: str
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "competency": self.competency,
            "question": self.text,
            "rationale": self.rationale,
        }


@dataclass
class InterviewResponse:
    question_id: str
    answer: str
    mode: str = "written"            # written | audio | video
    duration_sec: float = 0.0
    words_per_minute: float = 0.0
    has_face: bool = False            # set true when the candidate keeps the camera on
    media_meta: dict = field(default_factory=dict)


@dataclass
class ScoredAnswer:
    question_id: str
    competency: str
    question: str
    answer: str
    score: int                       # 0-100
    signals: dict[str, float]        # rubric breakdown
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    follow_up: str = ""
    # New multi-dim scoring
    mode: str = "written"
    duration_sec: float = 0.0
    subscores: dict[str, int] = field(default_factory=dict)     # technical, communication, expression, structure, ownership
    presentation_signals: dict[str, float] = field(default_factory=dict)  # pace_wpm, filler_density, confidence_words, hedge_words, sentiment

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class InterviewSummary:
    overall_score: int
    band: str                         # "strong" | "moderate" | "weak"
    recommendation: str               # "advance" | "second_round" | "no_hire"
    strengths: list[str]
    risks: list[str]
    narrative: str
    competency_scores: dict[str, int]
    answers: list[dict]
    fairness_note: str
    # New roll-ups
    dimension_scores: dict[str, int] = field(default_factory=dict)  # technical, communication, expression, structure, ownership
    modes_used: list[str] = field(default_factory=list)
    total_duration_sec: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------
def _detect_role_bucket(job_title: str, job_description: str) -> str:
    text = f"{job_title} {job_description}".lower()
    if any(t in text for t in ["engineer", "developer", "swe", "software"]):
        return "engineer"
    if any(t in text for t in ["manager", "director", "head of", "lead"]):
        return "manager"
    if "sales" in text or "account executive" in text:
        return "sales"
    if "hr" in text or "people" in text or "recruit" in text:
        return "hr"
    if "designer" in text or "design" in text:
        return "designer"
    if "data" in text or "analyst" in text or "scientist" in text:
        return "data"
    return ""


def _local_question_set(job_title: str, job_description: str, resume_text: str, n_questions: int) -> list[InterviewQuestion]:
    bucket = _detect_role_bucket(job_title, job_description)
    job_skills, _ = extract_skills(job_description)
    resume_skills, _ = extract_skills(resume_text)
    gap = sorted(job_skills - resume_skills)

    qs: list[InterviewQuestion] = []
    used_text: set[str] = set()

    def _add(qid: str, comp: str, text: str, rationale: str = "") -> None:
        if text in used_text:
            return
        used_text.add(text)
        qs.append(InterviewQuestion(id=qid, competency=comp, text=text, rationale=rationale))

    # 1. role-specific opener
    if bucket and ROLE_SPECIFIC_HINTS.get(bucket):
        _add(f"q-role-1", "role_fit", ROLE_SPECIFIC_HINTS[bucket][0],
             f"Targeted to {bucket} archetype detected from job description.")
        _add(f"q-tech-1", "technical_depth", ROLE_SPECIFIC_HINTS[bucket][1],
             "Probes depth specific to the discipline.")

    # 2. skill-gap probe if there is a missing required skill
    if gap:
        skill = gap[0]
        _add("q-skill-gap-1", "technical_depth",
             f"Your resume does not call out {skill}. Walk me through any exposure you have to it and how you would ramp.",
             f"Resume did not mention required skill: {skill}. Closing the gap.")

    # 3. always include problem solving + ownership + communication
    _add("q-ps-1", "problem_solving", GENERIC_QUESTIONS["problem_solving"][0])
    _add("q-own-1", "ownership", GENERIC_QUESTIONS["ownership"][0])
    _add("q-comm-1", "communication", GENERIC_QUESTIONS["communication"][0])

    # 4. collaboration + values
    _add("q-collab-1", "collaboration", GENERIC_QUESTIONS["collaboration"][0])
    _add("q-values-1", "values_alignment", GENERIC_QUESTIONS["values_alignment"][0])

    return qs[:n_questions]


def _llm_question_set(job_title: str, job_description: str, resume_text: str, n_questions: int) -> Optional[list[InterviewQuestion]]:
    if llm_complete is None:
        return None
    try:
        prompt = textwrap.dedent(f"""
            Generate {n_questions} structured interview questions for the following role.
            Each question must target a single competency from this list:
            {', '.join(COMPETENCIES)}.

            Job title: {job_title}
            Job description:
            {job_description[:1800]}

            Candidate resume (may be partial):
            {resume_text[:1800]}

            Return JSON only, no prose. Schema:
            {{"questions": [
              {{"id": "q-1", "competency": "role_fit", "question": "…", "rationale": "…"}}
            ]}}
        """).strip()
        raw = llm_complete(prompt, system="You are a calibrated hiring interviewer. Keep questions specific and bias-free.")
        # Best-effort JSON parse
        import json
        # strip code fences if present
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        data = json.loads(cleaned)
        out: list[InterviewQuestion] = []
        for q in data.get("questions", []):
            out.append(
                InterviewQuestion(
                    id=str(q.get("id") or f"q-{len(out)+1}"),
                    competency=str(q.get("competency") or "role_fit"),
                    text=str(q.get("question") or "").strip(),
                    rationale=str(q.get("rationale") or "").strip(),
                )
            )
        return out[:n_questions] if out else None
    except (LLMError, Exception):
        return None


def generate_questions(
    job_title: str,
    job_description: str,
    resume_text: str = "",
    n_questions: int = 7,
    provider: str = "auto",
) -> list[InterviewQuestion]:
    """Generate an interview question set.

    provider="auto" tries LLM first, falls back to local.
    """
    if provider in ("auto", "llm"):
        out = _llm_question_set(job_title, job_description, resume_text, n_questions)
        if out:
            return out
    return _local_question_set(job_title, job_description, resume_text, n_questions)


# ---------------------------------------------------------------------------
# Response scoring
# ---------------------------------------------------------------------------
_FILLER_PATTERN = re.compile(r"\b(um+|uh+|like|you know|kinda|sort of)\b", re.IGNORECASE)
_STAR_HINTS = ["situation", "task", "action", "result", "outcome", "impact"]

# Multi-dim language signals
_CONFIDENCE_PATTERN = re.compile(
    r"\b(i led|i owned|i drove|i shipped|i delivered|i decided|i built|i designed|i architected|i mentored|i hired|i scaled|i grew)\b",
    re.IGNORECASE,
)
_HEDGE_PATTERN = re.compile(
    r"\b(maybe|kinda|sort of|i think|i guess|perhaps|possibly|might|probably|hopefully)\b",
    re.IGNORECASE,
)
_POSITIVE_PATTERN = re.compile(
    r"\b(succeeded|improved|exceeded|achieved|launched|delivered|won|grew|optimi[sz]ed|reduced|saved|learnt|learned)\b",
    re.IGNORECASE,
)
_NEGATIVE_PATTERN = re.compile(
    r"\b(failed|struggled|couldn't|wasn't able|missed|broke|regretted|messed up)\b",
    re.IGNORECASE,
)
# Technical depth proxy — words an interviewer values regardless of role.
_TECHNICAL_DEPTH_PATTERN = re.compile(
    r"\b(api|database|latency|throughput|cache|queue|architecture|migration|test|ci|cd|pipeline|"
    r"benchmark|metric|kpi|funnel|cohort|model|feature|customer|stakeholder|tradeoff|trade-off|design|decision)\b",
    re.IGNORECASE,
)
# Real ownership requires "I + action verb" pairs, not just the pronoun "I".
_OWNERSHIP_PHRASE_PATTERN = re.compile(
    r"\bi\s+(?:led|own(?:ed)?|drove|drive|shipped|ship|built|build|designed|design|architected|"
    r"delivered|deliver|launched|launch|mentored|mentor|managed|manage|hired|hire|scaled|scale|"
    r"grew|grow|reduced|reduce|improved|improve|saved|save|negotiated|negotiate|"
    r"decided|decide|coached|coach|debugged|debug|wrote|write|refactored|refactor|"
    r"automated|automate|migrated|migrate|spec(?:'?d|ed|ked)|presented|present|"
    r"prototyped|prototype|orchestrated|orchestrate|rolled|roll)\b",
    re.IGNORECASE,
)
# Non-answer / refusal / pass-through patterns. Designed to match only
# unambiguous refusals — words like "test" or "pass" alone aren't enough
# because they appear in legitimate technical answers ("test harness",
# "we made a single pass through the array").
_REFUSAL_PATTERN = re.compile(
    r"\b("
    r"i\s+(?:don'?t|do\s+not|cannot|can'?t|won'?t|will\s+not|wouldn'?t|haven'?t)\s+"
    r"(?:know|do|did|have|remember|recall|want|like|care)"
    r"|i\s+have\s+(?:no|nothing)\s+(?:idea|answer|experience)"
    r"|no\s+idea"
    r"|not\s+(?:sure|applicable)"
    r"|n\/?a"
    r"|skip\s+(?:this|question|that)"
    r"|next\s+question"
    r"|just\s+test(?:ing)?(?:\s+this|\s+the)?"
    r"|this\s+is\s+(?:a\s+)?test"
    r"|i'?m\s+(?:just\s+)?test(?:ing)?"
    r"|asdf|qwerty|hello\s+world|lorem\s+ipsum"
    r"|i\s+(?:do\s+not|don'?t)\s+do\s+(?:it|this|that)"
    r"|don'?t\s+know"
    r")\b",
    re.IGNORECASE,
)
# Standalone single-word non-answers (matched only when the WHOLE answer is one of these).
_STANDALONE_NONANSWERS = {"skip", "pass", "none", "nothing", "nope", "nada", "idk", "dunno", "n/a", "na"}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return max(0.0, min(1.0, dot / (na * nb))) if na and nb else 0.0


def _rubric_signals(question: str, answer: str) -> dict[str, float]:
    """Cheap rubric. Each signal is 0..1 and is recombined upstream."""
    answer = (answer or "").strip()
    words = answer.split()
    wc = len(words)

    # length / depth
    length_score = 0.0
    if wc >= 60:
        length_score = 1.0
    elif wc >= 30:
        length_score = 0.7
    elif wc >= 15:
        length_score = 0.4
    elif wc >= 8:
        length_score = 0.15
    else:
        length_score = 0.0  # below 8 words isn't an answer

    # specificity — presence of numbers, proper nouns, dates
    specifics = len(re.findall(r"\b\d{2,4}\b", answer)) + len(re.findall(r"\b[A-Z][a-zA-Z]+\b", answer))
    specificity_score = min(1.0, specifics / 6.0)

    # STAR framing
    a_lower = answer.lower()
    star_hits = sum(1 for h in _STAR_HINTS if h in a_lower)
    star_score = min(1.0, star_hits / 4.0)

    # ownership — first-person paired with action verbs (e.g. "I led", "I shipped").
    # Bare pronoun "I" no longer counts; saying "I do not do it" can't claim ownership.
    ownership_hits = len(_OWNERSHIP_PHRASE_PATTERN.findall(answer))
    ownership_score = min(1.0, ownership_hits / 3.0)
    # Require some length too — a 5-word answer can't really demonstrate ownership.
    if wc < 15:
        ownership_score *= wc / 15.0

    # clarity = (no fillers) * (enough length to demonstrate clarity)
    # An empty / 3-word reply has nothing to be "clear" about — don't auto-award 1.0.
    fillers = len(_FILLER_PATTERN.findall(answer))
    filler_penalty = max(0.0, 1.0 - (fillers / max(wc, 1)) * 4)
    if wc < 8:
        length_factor = 0.0
    elif wc < 25:
        length_factor = wc / 25.0
    else:
        length_factor = 1.0
    clarity_score = filler_penalty * length_factor

    return {
        "length": length_score,
        "specificity": specificity_score,
        "star_framing": star_score,
        "ownership": ownership_score,
        "clarity": clarity_score,
    }


def _refusal_score(answer: str) -> float:
    """0..1 estimate of how non-answer-like the response is.

    1.0 = clearly a refusal / placeholder / non-answer.
    0.0 = looks like a real attempt.

    Scaled by answer length so a 100-word answer that happens to contain
    one refusal-shaped phrase ("I don't know exactly how big it was, but…")
    isn't flagged as a refusal.
    """
    answer = (answer or "").strip()
    words = answer.split()
    wc = len(words)

    # Empty / 1-2 word reply is always a non-answer.
    if wc == 0:
        return 1.0
    if wc <= 3:
        return 0.95

    # Single standalone "skip" / "pass" / "none" replies (after stripping punctuation)
    stripped = re.sub(r"[^a-z0-9/]", "", answer.lower())
    if stripped in _STANDALONE_NONANSWERS:
        return 0.95

    refusal_hits = len(_REFUSAL_PATTERN.findall(answer))
    refusal_word_count = sum(len(m.split()) for m in _REFUSAL_PATTERN.findall(answer))
    # Share of the answer that is refusal-language.
    refusal_density = refusal_word_count / max(wc, 1)

    if wc < 8:
        brevity_signal = 1.0 - (wc - 3) / 5.0  # 4 words → 0.8, 7 → 0.2
    else:
        brevity_signal = 0.0

    # If the answer is dominated by refusal phrases (most of the words),
    # treat as a hard refusal regardless of length.
    if refusal_hits and wc <= 12:
        return min(1.0, 0.6 + 0.1 * refusal_hits + brevity_signal * 0.3)

    # For longer answers, only flag as refusal when the density is high.
    if refusal_density >= 0.4:
        return min(1.0, 0.4 + refusal_density)
    elif refusal_density >= 0.2:
        return min(0.5, refusal_density)

    return brevity_signal


def _semantic_alignment(question: str, answer: str) -> float:
    try:
        return _cosine(embedding(question), embedding(answer))
    except Exception:
        return 0.0


def _presentation_signals(answer: str, duration_sec: float, mode: str) -> dict[str, float]:
    """Pace + filler + confidence + hedge + sentiment from the transcript."""
    answer = (answer or "").strip()
    words = answer.split()
    wc = max(len(words), 1)
    fillers = len(_FILLER_PATTERN.findall(answer))
    confidence = len(_CONFIDENCE_PATTERN.findall(answer))
    hedges = len(_HEDGE_PATTERN.findall(answer))
    positives = len(_POSITIVE_PATTERN.findall(answer))
    negatives = len(_NEGATIVE_PATTERN.findall(answer))

    wpm = (wc / max(duration_sec / 60.0, 0.0001)) if duration_sec else 0.0

    # Sentiment proxy in [-1, 1]
    sentiment_score = (positives - negatives) / max(positives + negatives + 1, 1)

    return {
        "pace_wpm": round(wpm, 1) if duration_sec else 0.0,
        "filler_density": round(fillers / wc, 3),
        "confidence_words": confidence,
        "hedge_words": hedges,
        "positives": positives,
        "negatives": negatives,
        "sentiment": round(sentiment_score, 2),
        "word_count": wc,
    }


def _technical_score(question: str, answer: str, semantic: float) -> int:
    """Technical depth: semantic + role keyword density + numeric/proper-noun specificity."""
    keywords = len(_TECHNICAL_DEPTH_PATTERN.findall(answer))
    specifics = len(re.findall(r"\b\d{1,5}(?:\.\d+)?(?:%|x|\b)", answer))
    kw_score = min(1.0, keywords / 6.0)
    sp_score = min(1.0, specifics / 4.0)
    combined = 0.5 * semantic + 0.30 * kw_score + 0.20 * sp_score
    return int(round(combined * 100))


def _communication_score(presentation: dict, signals: dict) -> int:
    """Communication: clarity (filler) * length * pace * structure.

    The previous formula auto-credited pace=0.6 when no duration was set, which
    inflated short non-answers. We now require real signal across all four
    dimensions and floor the score when there's almost no content.
    """
    pace_wpm = presentation.get("pace_wpm", 0.0)
    wc = presentation.get("word_count", 0)
    # Ideal pace 110-170 wpm; penalise too slow or too fast
    if pace_wpm <= 0:
        # No duration captured (written / very brief): score from text alone.
        pace_score = 0.4
    elif 110 <= pace_wpm <= 170:
        pace_score = 1.0
    elif 90 <= pace_wpm < 110 or 170 < pace_wpm <= 200:
        pace_score = 0.75
    elif pace_wpm < 50:
        pace_score = 0.15
    else:
        pace_score = 0.45

    clarity = signals.get("clarity", 0.0)
    length = signals.get("length", 0.0)
    star = signals.get("star_framing", 0.0)
    combined = 0.35 * clarity + 0.25 * pace_score + 0.20 * star + 0.20 * length

    # Hard floor: <8 words can't meaningfully demonstrate communication.
    if wc < 8:
        combined *= wc / 16.0  # 0 → 0, 7 → 0.44 max
    return int(round(combined * 100))


def _expression_score(presentation: dict, mode: str, has_face: bool) -> int:
    """Expression / presence: sentiment + confidence vs. hedging + presence bonus for video.

    Previously the formula awarded ~35% just for *absence* of negative signal
    (no hedges + neutral sentiment + zero confidence words still gave 0.35).
    We now require real expression signal and scale by answer length so a
    3-word refusal cannot inherit a 70 expression score from "no negatives".
    """
    confidence = presentation.get("confidence_words", 0)
    hedges = presentation.get("hedge_words", 0)
    positives = presentation.get("positives", 0)
    negatives = presentation.get("negatives", 0)
    sentiment = presentation.get("sentiment", 0.0)
    wc = presentation.get("word_count", 1)

    # Density per ~40-word chunk
    chunk = max(wc / 40.0, 1.0)
    confidence_density = min(1.0, confidence / chunk)
    positive_density = min(1.0, positives / chunk)
    hedge_density = min(1.0, hedges / chunk)
    negative_density = min(1.0, negatives / chunk)

    # Real evidence of expression: confident verbs + positive outcomes.
    positive_signal = 0.6 * confidence_density + 0.4 * positive_density
    # Penalty for hedging (without ownership) and negative framing.
    hedge_penalty = min(0.5, 0.6 * hedge_density + 0.2 * negative_density)
    if confidence == 0 and hedges > 0:
        hedge_penalty = min(0.7, hedge_penalty + 0.2)

    # Sentiment is a small modifier only when there's real expression signal.
    sentiment_modifier = 0.0
    if positive_signal > 0.1:
        sentiment_modifier = max(0.0, sentiment) * 0.15

    base = positive_signal + sentiment_modifier - hedge_penalty
    base = max(0.0, min(1.0, base))

    # Length gate — a 3-word reply cannot earn full expression credit.
    if wc < 8:
        base *= wc / 16.0
    elif wc < 20:
        base *= 0.5 + (wc - 8) / 24.0  # 8 → 0.5, 20 → 1.0

    # Presence bonus only for video where the candidate kept the camera on
    # AND there is real expression signal to amplify.
    if mode == "video" and has_face and base > 0.15:
        base = min(1.0, base + 0.05)
    elif mode == "written":
        base *= 0.85  # written can't fully demonstrate expression

    return int(round(base * 100))


def _structure_score(signals: dict) -> int:
    """STAR + ownership."""
    star = signals.get("star_framing", 0.0)
    ownership = signals.get("ownership", 0.0)
    spec = signals.get("specificity", 0.0)
    combined = 0.5 * star + 0.3 * ownership + 0.2 * spec
    return int(round(combined * 100))


def score_answer(
    question: InterviewQuestion,
    answer: str,
    *,
    mode: str = "written",
    duration_sec: float = 0.0,
    has_face: bool = False,
) -> ScoredAnswer:
    signals = _rubric_signals(question.text, answer)
    semantic = _semantic_alignment(question.text, answer)
    presentation = _presentation_signals(answer, duration_sec, mode)
    refusal = _refusal_score(answer)

    # Multi-dim subscores (0-100)
    technical = _technical_score(question.text, answer, semantic)
    communication = _communication_score(presentation, signals)
    expression = _expression_score(presentation, mode, has_face)
    structure = _structure_score(signals)
    ownership_score = int(round(signals.get("ownership", 0.0) * 100))

    # Refusal / non-answer attenuation — apply BEFORE blending so the per-dim
    # numbers themselves reflect reality (otherwise the dimension roll-up at
    # the end would still report a misleading 60-70 expression for a refusal).
    if refusal > 0.0:
        keep = max(0.0, 1.0 - refusal)
        technical = int(round(technical * keep))
        communication = int(round(communication * keep))
        expression = int(round(expression * keep))
        structure = int(round(structure * keep))
        ownership_score = int(round(ownership_score * keep))

    # Overall — weighted blend
    weights = {
        "technical": 0.35,
        "communication": 0.25,
        "expression": 0.15,
        "structure": 0.15,
        "ownership": 0.10,
    }
    blended = (
        weights["technical"] * technical
        + weights["communication"] * communication
        + weights["expression"] * expression
        + weights["structure"] * structure
        + weights["ownership"] * ownership_score
    )
    score = int(round(blended))

    # Hard cap when the answer is essentially a non-answer.
    if refusal >= 0.95:
        score = min(score, 5)
    elif refusal >= 0.7:
        score = min(score, 12)
    elif refusal >= 0.4:
        score = min(score, 25)

    subscores = {
        "technical": technical,
        "communication": communication,
        "expression": expression,
        "structure": structure,
        "ownership": ownership_score,
    }

    strengths: list[str] = []
    gaps: list[str] = []

    # Refusal feedback overrides the usual breakdown so reviewers see *why*
    # the score is near zero.
    if refusal >= 0.7:
        gaps.append(
            "Candidate did not provide a substantive answer (refusal / non-answer detected). "
            "Re-ask with a specific prompt: 'walk me through one concrete example.'"
        )
    elif refusal >= 0.4:
        gaps.append(
            "Answer is very brief and may not be a real attempt — re-ask for a concrete example."
        )
    else:
        if technical >= 65:
            strengths.append("Strong technical depth — specific decisions and trade-offs.")
        else:
            gaps.append("Light on technical specifics — probe for architecture / metrics / decisions.")

        if communication >= 70:
            strengths.append("Clear, well-paced communication.")
        else:
            if presentation.get("pace_wpm", 0) > 200:
                gaps.append("Pace is fast — slow down to land the key points.")
            elif 0 < presentation.get("pace_wpm", 0) < 100:
                gaps.append("Pace is slow — tighten the answer.")
            if presentation.get("filler_density", 0) > 0.04:
                gaps.append("Filler density above 4% — coach on concise phrasing.")
            if not gaps:
                gaps.append("Communication is functional but could be sharper.")

        if expression >= 60:
            strengths.append("Confident, positive framing.")
        elif presentation.get("hedge_words", 0) > 0 and presentation.get("confidence_words", 0) == 0:
            gaps.append("Heavy hedging without ownership language — ask for a concrete win.")

        if structure >= 60:
            strengths.append("Structured response (STAR + ownership).")
        else:
            gaps.append("Missing clear outcome — ask 'what was the measurable result?'")

        if semantic >= 0.5:
            strengths.append("Directly addresses the question asked.")
        elif semantic > 0:
            gaps.append("Answer drifts from the question — consider re-asking.")

    follow_up = ""
    if gaps:
        follow_up = "Suggested follow-up: " + gaps[0]

    merged_signals = {k: round(v, 3) for k, v in signals.items()}
    merged_signals["semantic_alignment"] = round(semantic, 3)
    merged_signals["refusal_score"] = round(refusal, 3)

    return ScoredAnswer(
        question_id=question.id,
        competency=question.competency,
        question=question.text,
        answer=answer,
        score=score,
        signals=merged_signals,
        strengths=strengths,
        gaps=gaps,
        follow_up=follow_up,
        mode=mode,
        duration_sec=duration_sec,
        subscores=subscores,
        presentation_signals=presentation,
    )


def summarize_interview(
    job_title: str,
    questions: list[InterviewQuestion],
    answers: list[InterviewResponse],
) -> InterviewSummary:
    by_qid: dict[str, InterviewQuestion] = {q.id: q for q in questions}
    scored: list[ScoredAnswer] = []
    for resp in answers:
        q = by_qid.get(resp.question_id)
        if not q:
            continue
        scored.append(score_answer(
            q,
            resp.answer,
            mode=resp.mode,
            duration_sec=resp.duration_sec,
            has_face=resp.has_face,
        ))

    if not scored:
        return InterviewSummary(
            overall_score=0,
            band="weak",
            recommendation="no_hire",
            strengths=[],
            risks=["No answers submitted."],
            narrative="Interview produced no scoreable answers.",
            competency_scores={},
            answers=[],
            fairness_note=(
                "AI scoring is assistive only. Final hiring decisions require human review. "
                "Do not use this output as the sole basis for an offer or rejection."
            ),
        )

    # competency aggregation
    comp_totals: dict[str, list[int]] = {}
    for s in scored:
        comp_totals.setdefault(s.competency, []).append(s.score)
    comp_scores = {c: int(round(sum(v) / len(v))) for c, v in comp_totals.items()}

    overall = int(round(sum(s.score for s in scored) / len(scored)))

    if overall >= 75:
        band, rec = "strong", "advance"
    elif overall >= 55:
        band, rec = "moderate", "second_round"
    else:
        band, rec = "weak", "no_hire"

    # narrative
    top_strengths: list[str] = []
    risks: list[str] = []
    for s in scored:
        top_strengths.extend(s.strengths)
        risks.extend(s.gaps)
    # dedupe while keeping order
    seen = set()
    top_strengths = [x for x in top_strengths if not (x in seen or seen.add(x))][:5]
    seen = set()
    risks = [x for x in risks if not (x in seen or seen.add(x))][:5]

    weakest = min(comp_scores.items(), key=lambda kv: kv[1]) if comp_scores else ("", 0)
    strongest = max(comp_scores.items(), key=lambda kv: kv[1]) if comp_scores else ("", 0)

    narrative = (
        f"Candidate produced a {band} overall interview ({overall}/100) for the {job_title} role. "
        f"Strongest competency: {strongest[0]} ({strongest[1]}). "
        f"Weakest: {weakest[0]} ({weakest[1]}). "
        f"Recommendation: {rec.replace('_', ' ')}."
    )

    fairness_note = (
        "This summary is generated by an AI scoring rubric and is intended to support — not replace — "
        "human interviewer judgement. Calibrate against structured rubric criteria and review for "
        "bias before any hiring decision. Sensitive attributes (age, gender, religion, family status, "
        "etc.) must not influence the final recommendation."
    )

    # Dimension roll-ups across all answers
    dim_totals: dict[str, list[int]] = {}
    for s in scored:
        for k, v in (s.subscores or {}).items():
            dim_totals.setdefault(k, []).append(v)
    dimension_scores = {k: int(round(sum(v) / len(v))) for k, v in dim_totals.items()}

    modes_used = sorted({s.mode for s in scored if s.mode})
    total_duration = round(sum(s.duration_sec for s in scored), 1)

    return InterviewSummary(
        overall_score=overall,
        band=band,
        recommendation=rec,
        strengths=top_strengths,
        risks=risks,
        narrative=narrative,
        competency_scores=comp_scores,
        answers=[s.to_dict() for s in scored],
        fairness_note=fairness_note,
        dimension_scores=dimension_scores,
        modes_used=modes_used,
        total_duration_sec=total_duration,
    )
