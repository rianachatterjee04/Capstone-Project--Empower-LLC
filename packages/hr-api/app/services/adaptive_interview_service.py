"""Adaptive Interview Engine.

This is the brain that makes the AI interviewer *adaptive* instead of a fixed
question list. It anchors a session on a RUBRIC (the competencies for the
role), tracks per-competency COVERAGE as the candidate answers, and — after
every answer — decides the next move DETERMINISTICALLY:

    probe · follow_up · pivot · clarify · wrap_up

then generates the next question for that move.

DESIGN PRINCIPLES
-----------------
1. REUSE, DON'T DUPLICATE. Answer *scoring* is delegated to the existing
   ``ai_interview_service.score_answer`` (multi-dimensional, refusal-aware).
   This module adds the layer on top: quality classification, coverage state,
   next-move logic, and adaptive question generation.

2. FAIL-SOFT. Question generation tries the LLM (``app.services.llm``, the
   fail-soft AI client) first and falls back to a curated per-competency
   question LADDER (easy → medium → hard) so an interview NEVER breaks
   mid-session, even with no API key. Answer analysis is fully deterministic so
   the session is reproducible and testable.

3. DETERMINISTIC + EXPLAINABLE. The next-move decision is a pure function of
   the analysis + coverage state (see ``choose_next_move``). Every transition
   is auditable.

COVERAGE / STOP MODEL
---------------------
Each competency carries ``signal_strength`` in [0,1] and a ``probes`` count.
On each answer for competency C:

    answer_signal   = (score/100) * QUALITY_WEIGHT[quality]
    signal_strength = old + (1 - old) * answer_signal      # monotone, bounded

A competency is *sufficiently covered* at ``signal_strength >= SUFFICIENT``.
The interview WRAPS UP when every rubric competency is sufficient, OR the
max-question cap is hit — whichever comes first.
"""
from __future__ import annotations

import re
from typing import Optional

from app.services.ai_interview_service import InterviewQuestion, ScoredAnswer, score_answer

try:  # the fail-soft AI client — absent/erroring falls back to the ladder
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


# ---------------------------------------------------------------------------
# Tunables (documented so a reviewer can audit the thresholds)
# ---------------------------------------------------------------------------
SUFFICIENT_SIGNAL = 0.6          # competency "covered" at >= this signal strength
MAX_PROBES_PER_COMPETENCY = 3    # stop grinding one competency after N probes
DEFAULT_MAX_QUESTIONS = 12       # hard cap on total questions per session

# How much a single answer moves a competency's signal, by answer quality.
QUALITY_WEIGHT = {
    "strong": 1.0,
    "shallow": 0.55,
    "vague": 0.25,
    "off_topic": 0.10,
}

# Moves
PROBE = "probe"
FOLLOW_UP = "follow_up"
PIVOT = "pivot"
CLARIFY = "clarify"
WRAP_UP = "wrap_up"


# ---------------------------------------------------------------------------
# Curated question LADDER — the fail-soft fallback (easy → medium → hard)
# ---------------------------------------------------------------------------
QUESTION_LADDER: dict[str, list[str]] = {
    "role_fit": [
        "To start, what attracted you to this role?",
        "Walk me through the project you're most proud of and why it mattered.",
        "Where do you see the hardest part of this role for you, and how would you get ahead of it?",
    ],
    "technical_depth": [
        "Tell me about a system or feature you've worked on recently.",
        "Describe a technical decision you made and the trade-offs you weighed.",
        "Take the most complex thing you've built — walk me through the architecture and where it would break at 10x scale.",
    ],
    "problem_solving": [
        "Tell me about a tricky problem you solved.",
        "Walk me through how you debugged a difficult issue under pressure.",
        "Describe a decision you made with incomplete information — how did you reason about the unknowns?",
    ],
    "communication": [
        "How do you explain something complex to a non-technical person?",
        "Give me an example where clear communication changed an outcome.",
        "Tell me about a time you had to align people who disagreed — how did you frame it?",
    ],
    "ownership": [
        "Tell me about something you owned end-to-end.",
        "Describe a time something went wrong that you owned. What did you do?",
        "What's an outcome you drove where nobody told you it was your job? What did you learn?",
    ],
    "collaboration": [
        "Tell me about a time you worked closely with a teammate.",
        "Describe a disagreement with a peer and how it resolved.",
        "Tell me about unblocking someone without doing the work for them.",
    ],
    "values_alignment": [
        "What kind of environment helps you do your best work?",
        "Tell me about feedback that changed how you operate.",
        "When have you pushed back on a leader because it conflicted with your values?",
    ],
    "motivation": [
        "Why this role, and why now?",
        "What would have to be true at month 6 for this to feel like a great move?",
        "What part of this work would you keep doing even if you weren't paid for it?",
    ],
    "code_quality": [
        "How do you know when code is 'done'?",
        "Give a concrete example of when you decided quality over speed.",
        "Walk me through how you'd raise the quality bar on a team that's shipping too fast.",
    ],
    "system_design": [
        "Sketch how you'd approach a system for this role on day one.",
        "What would you defer to day-90, and why?",
        "Where's the first bottleneck in that design under real load, and how do you address it?",
    ],
    "team_fit": [
        "What do you need from a manager to do your best work?",
        "Describe the team dynamic where you've thrived.",
        "Tell me about joining a team mid-flight — how did you earn trust?",
    ],
    "self_awareness": [
        "What's a useful piece of feedback you received?",
        "What did you change because of it?",
        "What's a pattern in your own work you're actively trying to improve?",
    ],
    "feedback": [
        "Tell me about giving someone hard feedback.",
        "How did you frame it, and what happened?",
        "Describe a time feedback you gave didn't land — what did you do next?",
    ],
    "scope": [
        "What's the largest thing you've owned?",
        "Put numbers on it — scope, headcount, dollars.",
        "Where did the scale of it force you to change how you worked?",
    ],
    "judgment": [
        "Tell me about a high-stakes call you made.",
        "How did you weigh the trade-offs with limited information?",
        "Looking back, what would you decide differently, and why?",
    ],
    "long_term_fit": [
        "What does the next couple of years look like for you?",
        "Where does this role land in that?",
        "What would make you want to stay and grow here for the long run?",
    ],
    "compensation_alignment": [
        "What are your expectations on compensation structure?",
        "How do you weigh base vs. equity vs. variable?",
        "What would make an overall package feel right to you beyond the number?",
    ],
    "logistics": [
        "What's your timeline and start-date flexibility?",
        "Anything about location or schedule we should plan around?",
        "Is there anything that would need to be true logistically for this to work?",
    ],
    "_generic": [
        "Tell me a bit more about your experience here.",
        "Give me a concrete example with specifics.",
        "Walk me through the hardest version of that you've handled.",
    ],
}

# Move-specific templates — a follow-up asks for the missing specifics, a
# clarify gently redirects an off-topic answer.
_FOLLOWUP_TEMPLATES = [
    "That's a start — can you give me one specific example, with the numbers or outcome, on {comp}?",
    "Let's make that concrete: walk me through exactly what you did and what the measurable result was.",
    "Can you go a level deeper — what was your specific role and the impact you can point to?",
]
_CLARIFY_TEMPLATES = [
    "Let me refocus us a little — on {comp} specifically, can you share a real example from your own experience?",
    "I want to make sure I capture {comp} — could you tie your answer back to a concrete situation you handled?",
]


def _human(competency: str) -> str:
    return (competency or "").replace("_", " ").strip() or "this area"


# ---------------------------------------------------------------------------
# Answer analysis (deterministic; reuses ai_interview_service.score_answer)
# ---------------------------------------------------------------------------
_STOPWORDS = {
    "about", "walk", "tell", "give", "your", "you", "the", "and", "that", "this",
    "with", "have", "would", "could", "what", "when", "were", "them", "they",
    "from", "into", "most", "made", "make", "time", "example", "please", "recent",
    "recently", "describe", "through", "their", "there", "which", "some", "any",
    "how", "why", "did", "was", "are", "for",
}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _STOPWORDS}


def topical_overlap(question: str, answer: str) -> int:
    """Embedding-independent relevance proxy: count of shared content words
    between the question and the answer. Robust in demo mode where mock
    embeddings make cosine similarity uninformative."""
    return len(_content_words(question) & _content_words(answer))


def classify_quality(scored: ScoredAnswer) -> str:
    """Map a scored answer to one of: strong · shallow · vague · off_topic.

    Deterministic and reproducible. Uses signals that stay reliable even in
    demo mode (mock embeddings): the refusal detector, the lexical
    sub-dimension scores, and a question/answer content-word overlap. Semantic
    cosine is used only as a secondary confirmation, since it is noise under
    mock embeddings.
    """
    signals = scored.signals or {}
    refusal = float(signals.get("refusal_score", 0.0))
    semantic = float(signals.get("semantic_alignment", 0.0))
    wc = int((scored.presentation_signals or {}).get("word_count", 0))
    subs = scored.subscores or {}

    # 1. Refusal / evasive / placeholder / empty → vague.
    if refusal >= 0.5:
        return "vague"

    # 2. A real attempt that doesn't engage the question → off_topic.
    #    Signalled by ZERO shared content words with the question (and, if
    #    real embeddings are wired, weak cosine too).
    overlap = topical_overlap(scored.question, scored.answer)
    if wc >= 8 and overlap == 0 and semantic < 0.35:
        return "off_topic"

    # 3. Strong: real depth on the reliable lexical dimensions + enough content.
    depth = max(subs.get("technical", 0), subs.get("structure", 0), subs.get("ownership", 0))
    if depth >= 50 and subs.get("communication", 0) >= 45 and wc >= 30:
        return "strong"

    # 4. Everything else is a shallow-but-on-topic answer worth probing.
    return "shallow"


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NUMERIC = re.compile(r"\b\d")
_OWNERSHIP = re.compile(r"\bi\s+\w+", re.IGNORECASE)


def extract_evidence(answer: str, *, max_quotes: int = 2) -> list[str]:
    """Pull the most evidence-bearing sentences (numbers / first-person action)."""
    answer = (answer or "").strip()
    if not answer:
        return []
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(answer) if s.strip()]
    scored: list[tuple[int, str]] = []
    for s in sentences:
        weight = 0
        if _NUMERIC.search(s):
            weight += 2
        if _OWNERSHIP.search(s):
            weight += 1
        if len(s.split()) >= 8:
            weight += 1
        if weight:
            scored.append((weight, s))
    scored.sort(key=lambda t: (-t[0], sentences.index(t[1])))
    quotes = [s for _, s in scored[:max_quotes]]
    if not quotes and sentences:
        quotes = [sentences[0]]
    return quotes


def analyze_answer(
    question: InterviewQuestion,
    answer: str,
    *,
    mode: str = "written",
    duration_sec: float = 0.0,
    has_face: bool = False,
) -> dict:
    """Analyze a single answer against its competency.

    Returns a compact, JSON-serialisable analysis:
        {quality, competency, score, evidence, subscores, signals}
    Fully deterministic (fail-soft): built on the existing scorer.
    """
    scored = score_answer(question, answer, mode=mode, duration_sec=duration_sec, has_face=has_face)
    quality = classify_quality(scored)
    evidence = extract_evidence(answer)
    return {
        "quality": quality,
        "competency": question.competency,
        "score": scored.score,
        "evidence": evidence,
        "subscores": scored.subscores,
        "signals": scored.signals,
        "strengths": scored.strengths,
        "gaps": scored.gaps,
    }


# ---------------------------------------------------------------------------
# Coverage state
# ---------------------------------------------------------------------------
def init_coverage(rubric: list[str]) -> dict[str, dict]:
    """Fresh coverage map: one entry per rubric competency."""
    out: dict[str, dict] = {}
    for comp in rubric:
        if comp not in out:
            out[comp] = {"signal_strength": 0.0, "probes": 0, "best_score": 0, "quality_history": []}
    return out


def _new_signal_strength(old: float, score: int, quality: str) -> float:
    """Monotone, bounded update: old + (1-old)*answer_signal."""
    weight = QUALITY_WEIGHT.get(quality, 0.4)
    answer_signal = (max(0, min(100, score)) / 100.0) * weight
    new = old + (1.0 - old) * answer_signal
    return round(max(0.0, min(1.0, new)), 4)


def update_coverage(coverage: dict[str, dict], competency: str, analysis: dict) -> dict:
    """Fold one analysis into the coverage map for its competency. Mutates + returns coverage."""
    entry = coverage.setdefault(
        competency, {"signal_strength": 0.0, "probes": 0, "best_score": 0, "quality_history": []}
    )
    entry["signal_strength"] = _new_signal_strength(
        entry["signal_strength"], int(analysis.get("score", 0)), analysis.get("quality", "shallow")
    )
    entry["probes"] += 1
    entry["best_score"] = max(int(entry.get("best_score", 0)), int(analysis.get("score", 0)))
    entry["quality_history"].append(analysis.get("quality", "shallow"))
    return coverage


def _least_covered(coverage: dict[str, dict], rubric: list[str]) -> Optional[str]:
    """The competency most in need of signal: lowest strength (< SUFFICIENT),
    tie-broken by fewest probes then rubric order. None if all are sufficient."""
    candidates = [c for c in rubric if coverage.get(c, {}).get("signal_strength", 0.0) < SUFFICIENT_SIGNAL]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (
            coverage.get(c, {}).get("signal_strength", 0.0),
            coverage.get(c, {}).get("probes", 0),
            rubric.index(c),
        ),
    )


def is_complete(coverage: dict[str, dict], rubric: list[str], asked_count: int, max_questions: int) -> bool:
    if asked_count >= max_questions:
        return True
    return all(coverage.get(c, {}).get("signal_strength", 0.0) >= SUFFICIENT_SIGNAL for c in rubric)


# ---------------------------------------------------------------------------
# Next-move decision (pure, deterministic — the heart of the engine)
# ---------------------------------------------------------------------------
def choose_next_move(
    coverage: dict[str, dict],
    *,
    last_competency: str,
    quality: str,
    rubric: list[str],
    asked_count: int,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
) -> dict:
    """Decide the next move + its target competency from the latest analysis.

    Decision table (evaluated top-down):
      max cap hit / all competencies sufficient         -> wrap_up
      off_topic                                          -> clarify   (same competency)
      vague|shallow  & probes < MAX                      -> follow_up (same competency)
      vague|shallow  & probes >= MAX                     -> pivot     (least covered)
      strong & under-explored (signal<SUFFICIENT, <MAX)  -> probe     (same competency)
      strong & sufficiently covered                      -> pivot     (least covered)
      pivot with nothing left to cover                   -> wrap_up
    """
    # Global stop conditions first.
    if asked_count >= max_questions:
        return {"move": WRAP_UP, "competency": None, "reason": "max_question_cap_reached"}
    if all(coverage.get(c, {}).get("signal_strength", 0.0) >= SUFFICIENT_SIGNAL for c in rubric):
        return {"move": WRAP_UP, "competency": None, "reason": "all_competencies_sufficient"}

    entry = coverage.get(last_competency, {"signal_strength": 0.0, "probes": 0})
    probes = int(entry.get("probes", 0))
    signal = float(entry.get("signal_strength", 0.0))

    def _pivot() -> dict:
        target = _least_covered(coverage, rubric)
        if target is None:
            return {"move": WRAP_UP, "competency": None, "reason": "nothing_left_to_cover"}
        return {"move": PIVOT, "competency": target, "reason": "pivot_to_least_covered"}

    if quality == "off_topic":
        return {"move": CLARIFY, "competency": last_competency, "reason": "answer_off_topic"}

    if quality in ("vague", "shallow"):
        if probes >= MAX_PROBES_PER_COMPETENCY:
            return _pivot()
        return {"move": FOLLOW_UP, "competency": last_competency, "reason": f"answer_{quality}_needs_specifics"}

    # quality == "strong"
    if signal < SUFFICIENT_SIGNAL and probes < MAX_PROBES_PER_COMPETENCY:
        return {"move": PROBE, "competency": last_competency, "reason": "strong_but_under_explored"}
    return _pivot()


# ---------------------------------------------------------------------------
# Acknowledgement (warm, human-feeling reaction for the candidate UI)
# ---------------------------------------------------------------------------
_ACK = {
    "strong": "That's a strong, concrete example — thank you.",
    "shallow": "Got it — let's go a level deeper on that.",
    "vague": "No problem. Let's make it concrete.",
    "off_topic": "Thanks — let me refocus us a little.",
}


def ack_for(quality: str) -> str:
    return _ACK.get(quality, "Thanks for that.")


# ---------------------------------------------------------------------------
# Next-question generation (LLM first, fail-soft to the curated ladder)
# ---------------------------------------------------------------------------
def _llm_next_question(
    *, move: str, competency: str, rubric: list[str], resume_text: str,
    transcript: str, org_id: Optional[str],
) -> Optional[str]:
    if llm_complete is None:
        return None
    try:
        move_intent = {
            PROBE: "probe deeper — the candidate is strong here but you need more signal",
            FOLLOW_UP: "ask a sharp follow-up for a specific example, number, or measurable outcome",
            PIVOT: "pivot to this new competency with a fresh, open question",
            CLARIFY: "gently redirect — the last answer drifted off-topic",
        }.get(move, "ask a good interview question")
        prompt = (
            f"You are conducting a live, adaptive interview. Ask ONE next question.\n"
            f"Target competency: {_human(competency)}\n"
            f"Move: {move_intent}.\n"
            f"Rubric competencies: {', '.join(_human(c) for c in rubric)}\n"
            f"Candidate resume (may be partial):\n{(resume_text or '')[:1200]}\n\n"
            f"Running transcript so far:\n{(transcript or '')[:2500]}\n\n"
            f"Return ONLY the question text — one sentence, warm and specific, no preamble."
        )
        raw = llm_complete(
            prompt,
            system="You are a calibrated, warm, bias-free human interviewer.",
            org_id=org_id,
        )
        text = (raw or "").strip().strip('"').split("\n")[0].strip()
        if text and len(text) > 8:
            return text
    except (LLMError, Exception):
        return None
    return None


def _ladder_question(*, move: str, competency: str, probes_on_comp: int, asked_texts: set[str]) -> str:
    # Move-specific templates for follow-up / clarify first.
    if move == FOLLOW_UP:
        for t in _FOLLOWUP_TEMPLATES:
            text = t.format(comp=_human(competency))
            if text not in asked_texts:
                return text
    elif move == CLARIFY:
        for t in _CLARIFY_TEMPLATES:
            text = t.format(comp=_human(competency))
            if text not in asked_texts:
                return text

    ladder = QUESTION_LADDER.get(competency) or QUESTION_LADDER["_generic"]
    # probe/pivot climb the ladder by how many probes already spent on the comp.
    start = min(max(probes_on_comp, 0), len(ladder) - 1)
    order = list(range(start, len(ladder))) + list(range(0, start))
    for i in order:
        if ladder[i] not in asked_texts:
            return ladder[i]
    return ladder[start]  # everything asked — repeat the current tier rather than break


def generate_next_question(
    *, move: str, competency: str, coverage: dict[str, dict], asked_texts: set[str],
    rubric: list[str], resume_text: str = "", transcript: str = "", org_id: Optional[str] = None,
) -> dict:
    """Generate the next question for a move. LLM first, curated ladder fallback.

    Returns {text, source, competency, move}. NEVER raises.
    """
    probes_on_comp = int(coverage.get(competency, {}).get("probes", 0))
    llm_text = _llm_next_question(
        move=move, competency=competency, rubric=rubric,
        resume_text=resume_text, transcript=transcript, org_id=org_id,
    )
    if llm_text and llm_text not in asked_texts:
        return {"text": llm_text, "source": "llm", "competency": competency, "move": move}
    text = _ladder_question(
        move=move, competency=competency, probes_on_comp=probes_on_comp, asked_texts=asked_texts
    )
    return {"text": text, "source": "ladder", "competency": competency, "move": move}


# ---------------------------------------------------------------------------
# Progress roll-up (for GET /state + the candidate progress indicator)
# ---------------------------------------------------------------------------
def _rating_0_4(score_0_100: int) -> int:
    """Map a 0-100 adaptive score onto the shared 0-4 rubric scale."""
    return max(0, min(4, int(round(max(0, min(100, score_0_100)) / 25.0))))


def build_explainable_outcome(
    org_id: str,
    interview_id: str,
    *,
    coverage: dict[str, dict],
    rubric: list[str],
    evidence_by_competency: dict[str, list[str]],
) -> dict:
    """Bridge the adaptive session into the SHARED explainable-scoring service.

    Synthesises an AI-authored scorecard from the coverage state (0-100 →
    0-4), submits it, then returns the reusable explainable breakdown from
    ``interview_score_review_service`` — the same weighted-sum + evidence +
    HITL-recourse contract used by the human-panel flow. This means a
    recruiter can open a HITL review on an adaptive score exactly like any
    other. Fail-soft: any error degrades to an unavailable-but-valid payload.
    """
    from app.services.interview_scorecard_service import (
        submit_scorecard,
        update_competency,
        upsert_scorecard,
    )
    from app.services.interview_score_review_service import build_explanation

    try:
        # Only score competencies we actually probed — unreached competencies
        # were never assessed and should not be counted as a zero.
        probed = [c for c in rubric if int(coverage.get(c, {}).get("probes", 0)) > 0]
        if not probed:
            probed = list(rubric)
        sc = upsert_scorecard(
            interview_id=interview_id,
            interviewer_id="ai-interviewer",
            interviewer_name="AI Interviewer",
            competencies=probed,
        )
        weights: dict[str, float] = {}
        composite_0_100 = 0.0
        for comp in probed:
            entry = coverage.get(comp, {})
            best = int(entry.get("best_score", 0))
            update_competency(
                interview_id=interview_id,
                scorecard_id=sc.id,
                competency=comp,
                rating=_rating_0_4(best),
                notes=f"Adaptive interview signal strength {entry.get('signal_strength', 0.0):.2f} "
                      f"over {entry.get('probes', 0)} probe(s).",
                evidence_snippets=evidence_by_competency.get(comp, [])[:3],
            )
            # weight competencies by how much signal we actually gathered.
            weights[comp] = max(float(entry.get("signal_strength", 0.0)), 0.05)
            composite_0_100 += best
        overall_0_100 = int(round(composite_0_100 / max(len(probed), 1)))
        recommendation = "hire" if overall_0_100 >= 65 else "no_hire" if overall_0_100 < 45 else "unsure"
        # Confidence: how much of the rubric we actually covered (1..5).
        covered = sum(1 for c in rubric if coverage.get(c, {}).get("signal_strength", 0.0) >= SUFFICIENT_SIGNAL)
        confidence = max(1, min(5, 1 + round(4 * covered / max(len(rubric), 1))))
        submit_scorecard(
            interview_id=interview_id,
            scorecard_id=sc.id,
            overall_rating=_rating_0_4(overall_0_100),
            overall_recommendation=recommendation,
            interviewer_confidence=confidence,
        )
        explanation = build_explanation(org_id, interview_id, weights)
        explanation["adaptive_overall_score"] = overall_0_100
        explanation["adaptive_recommendation"] = recommendation
        return explanation
    except Exception as exc:  # pragma: no cover — never break /complete
        return {
            "interview_id": interview_id,
            "available": False,
            "reason": f"explainable outcome unavailable ({exc.__class__.__name__})",
            "rubric": [],
            "overall_score": 0.0,
            "overall_confidence": 0.0,
        }


def coverage_progress(coverage: dict[str, dict], rubric: list[str]) -> dict:
    covered = [c for c in rubric if coverage.get(c, {}).get("signal_strength", 0.0) >= SUFFICIENT_SIGNAL]
    remaining = [c for c in rubric if c not in covered]
    per = [
        {
            "competency": c,
            "label": _human(c),
            "signal_strength": round(coverage.get(c, {}).get("signal_strength", 0.0), 4),
            "probes": int(coverage.get(c, {}).get("probes", 0)),
            "best_score": int(coverage.get(c, {}).get("best_score", 0)),
            "covered": coverage.get(c, {}).get("signal_strength", 0.0) >= SUFFICIENT_SIGNAL,
        }
        for c in rubric
    ]
    return {
        "competencies": per,
        "covered": covered,
        "remaining": remaining,
        "n_covered": len(covered),
        "n_total": len(rubric),
        "pct_covered": round(100.0 * len(covered) / max(len(rubric), 1), 1),
        "sufficient_threshold": SUFFICIENT_SIGNAL,
    }
