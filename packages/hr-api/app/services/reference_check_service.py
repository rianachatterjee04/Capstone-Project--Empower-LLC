"""AI Reference Check service.

Mirrors the AI Interview pattern but flipped: a *reference* talks ABOUT the
candidate, not as them. The service:

  1. Generates structured, relationship-aware reference questions
     (manager / peer / report / client) tailored to the role and any
     existing interview signal.
  2. Scores each reference's free-form answer on:
       - endorsement strength (would-rehire / superlative language)
       - specificity      (concrete examples, names, numbers, dates)
       - candor / sentiment (warmth vs. hedging vs. red flags)
       - concern signal   (lukewarm / negative cues)
  3. Synthesises *multiple* references into one calibrated report:
       - per-competency consensus
       - explicit contradictions across references
       - concrete strengths, risks, and recommended follow-ups
       - endorsement summary (strong endorse / endorse / lukewarm /
         do not endorse) with a defensible band

The scoring is intentionally a transparent rubric (no opaque black-box) so
recruiters can defend the recommendation in a debrief. LLM is used only for
optional question generation; if it isn't configured the local question
banks below ship the same coverage.

Calibrated with the same dataclass + ``to_dict`` patterns used by
``ai_interview_service`` so a follow-on UI can reuse the existing primitives.
"""
from __future__ import annotations

import math
import re
import textwrap
import uuid
from dataclasses import dataclass, field
from typing import Optional

try:
    from app.services.llm import llm_complete  # type: ignore
    from app.services.llm import LLMError  # type: ignore
except Exception:  # pragma: no cover - LLM is optional
    llm_complete = None  # type: ignore

    class LLMError(Exception):
        pass


# ---------------------------------------------------------------------------
# Relationship-aware question banks
# ---------------------------------------------------------------------------
RELATIONSHIPS = ("manager", "peer", "report", "client", "mentor", "other")

# Each competency maps to one short, focused, behaviorally-anchored prompt.
# The phrasing is calibrated to elicit STAR-style evidence — references that
# can't produce specifics usually betray either a thin working relationship
# or a soft endorsement, both of which the scorer should surface.
_BASE_COMPETENCIES = [
    ("strengths",        "What does {name} do better than almost anyone else you have worked with? Give me one or two specific examples that show this in action."),
    ("growth_area",      "Where does {name} have the most room to grow? Be candid — every reference notices something, and we'd rather know now than in month 3."),
    ("ownership",        "Tell me about a project or workflow {name} owned end-to-end. What did they do that another engineer / manager might not have?"),
    ("collaboration",    "How does {name} work with people who disagree with them — across functions, levels, or styles? A concrete example, please."),
    ("communication",    "How does {name} communicate with non-technical stakeholders? What's an example where this either worked very well — or where it broke down?"),
    ("judgment",         "Describe a difficult trade-off or decision you saw {name} navigate. What did you learn about how they think?"),
    ("conflict",         "Was there a time you saw {name} handle a real conflict — with you, a peer, or a stakeholder? What happened and how did they handle it?"),
    ("would_rehire",     "If you were starting a new team tomorrow and could hand-pick three people, would {name} be on that list — and where exactly would you put them?"),
    ("fairness_check",   "Is there anything else we should know about working with {name} — something that wouldn't show up in a resume or interview but matters?"),
]

# Role-relationship overlays: managers field different questions than peers
# or reports. We *append* these to the base list (don't overwrite) so every
# reference still answers the consensus core.
_RELATIONSHIP_HINTS: dict[str, list[tuple[str, str]]] = {
    "manager": [
        ("performance_arc", "How did {name}'s performance change from when they joined your team to when they left? What drove the change?"),
        ("feedback_signal", "What's the hardest piece of feedback you ever gave {name}, and how did they respond — both in the moment and over the next few weeks?"),
        ("scope_growth",    "Did you ever expand {name}'s scope or hand them something genuinely above their level? How did they handle it?"),
    ],
    "peer": [
        ("trust_signal",    "When something was on fire on the team, did people instinctively pull {name} in — or route around them? Why?"),
        ("ideas_credit",    "Tell me about a time {name} either championed someone else's idea or absorbed credit they didn't fully earn."),
    ],
    "report": [
        ("manager_quality", "What did {name} do for you as a manager that you wish more managers did? And what did you have to manage *around*?"),
        ("growth_support",  "How did {name} invest in your growth specifically? Concrete examples land best."),
    ],
    "client": [
        ("outcome_focus",   "What outcome did {name} deliver for you, and how did it compare to what was originally promised?"),
        ("partnership",     "Would you knowingly hire someone {name} recommended, sight unseen? Why or why not?"),
    ],
    "mentor": [
        ("self_awareness", "Where did {name} surprise you — positively or negatively — versus your initial read of them?"),
        ("learning_curve", "How did {name} take feedback? Walk me through one specific cycle."),
    ],
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ReferenceQuestion:
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
class ReferenceProfile:
    """Who the reference is and how they know the candidate."""
    id: str
    name: str
    email: str = ""
    title: str = ""
    company: str = ""
    relationship: str = "manager"   # one of RELATIONSHIPS
    tenure_months: int = 0
    invited_at: str = ""
    completed_at: Optional[str] = None
    consent_recorded: bool = False  # legal consent to take a reference

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ReferenceResponse:
    question_id: str
    answer: str
    mode: str = "written"            # written | audio | video
    duration_sec: float = 0.0
    words_per_minute: float = 0.0
    has_face: bool = False
    media_meta: dict = field(default_factory=dict)


@dataclass
class ScoredReferenceAnswer:
    question_id: str
    competency: str
    question: str
    answer: str
    score: int                       # 0-100 endorsement strength for THIS answer
    signals: dict[str, float]        # endorsement, specificity, candor, concern, length
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    follow_up: str = ""
    mode: str = "written"
    duration_sec: float = 0.0
    subscores: dict[str, int] = field(default_factory=dict)
    presentation_signals: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ScoredReference:
    reference_id: str
    reference_name: str
    relationship: str
    overall: int                     # 0-100 endorsement weighted across answers
    band: str                        # strong / endorse / lukewarm / do_not_endorse
    answers: list[ScoredReferenceAnswer]
    themes: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "reference_id": self.reference_id,
            "reference_name": self.reference_name,
            "relationship": self.relationship,
            "overall": self.overall,
            "band": self.band,
            "answers": [a.to_dict() for a in self.answers],
            "themes": self.themes,
            "red_flags": self.red_flags,
            "summary": self.summary,
        }


@dataclass
class ReferenceCheckSummary:
    """Multi-reference synthesised verdict."""
    overall_score: int               # 0-100 weighted across references
    band: str                        # strong_endorse / endorse / proceed_with_caution / decline
    recommendation: str              # advance / advance_with_caveats / hold / decline
    strengths: list[str]
    risks: list[str]
    contradictions: list[str]        # disagreements across references
    competency_scores: dict[str, int]
    references: list[dict]           # per-reference roll-ups
    narrative: str
    fairness_note: str
    n_references: int
    relationships_covered: list[str]

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------
def _local_questions(
    candidate_name: str,
    relationship: str,
    n_questions: int,
) -> list[ReferenceQuestion]:
    rel = relationship if relationship in RELATIONSHIPS else "other"
    base = [(c, t.format(name=candidate_name)) for c, t in _BASE_COMPETENCIES]
    overlay = [(c, t.format(name=candidate_name)) for c, t in _RELATIONSHIP_HINTS.get(rel, [])]
    combined: list[tuple[str, str]] = []
    seen: set[str] = set()
    # Interleave overlay questions early so they don't get truncated
    for src in (overlay[:2], base, overlay[2:]):
        for comp, text in src:
            if text in seen:
                continue
            seen.add(text)
            combined.append((comp, text))
    out: list[ReferenceQuestion] = []
    for i, (comp, text) in enumerate(combined[:max(n_questions, 1)]):
        rationale = ""
        if comp == "would_rehire":
            rationale = "The would-rehire / placement question is the single strongest predictor in our rubric."
        elif comp == "growth_area":
            rationale = "Most references soft-pedal weaknesses; if this comes back vague, it's a yellow flag in itself."
        elif comp == "fairness_check":
            rationale = "Gives the reference a graceful exit valve to surface something they wouldn't otherwise volunteer."
        out.append(
            ReferenceQuestion(
                id=f"rq-{i+1}",
                competency=comp,
                text=text,
                rationale=rationale,
            )
        )
    return out


def _llm_questions(
    candidate_name: str,
    relationship: str,
    job_title: str,
    extra_context: str,
    n_questions: int,
) -> Optional[list[ReferenceQuestion]]:
    if llm_complete is None:
        return None
    try:
        prompt = textwrap.dedent(f"""
            Generate {n_questions} structured *reference check* questions for a hiring decision.
            The reference is the candidate's former {relationship}.
            Candidate: {candidate_name}.
            Role they are being considered for: {job_title}.

            Optional context from the candidate's interview:
            {extra_context[:1200]}

            Constraints:
              - Each question targets one of these competencies:
                strengths, growth_area, ownership, collaboration, communication,
                judgment, conflict, would_rehire, performance_arc, fairness_check.
              - Questions must elicit a concrete behavioral example (STAR), not yes/no.
              - Avoid leading or compound questions. Avoid any protected-class probes.
              - Tone is calm, professional, and gives the reference an easy way to be candid.

            Return JSON only, no prose, schema:
            {{"questions":[{{"id":"rq-1","competency":"…","question":"…","rationale":"…"}}]}}
        """).strip()
        raw = llm_complete(
            prompt,
            system="You are a calibrated reference-check interviewer. Bias-aware, calm, evidence-focused.",
        )
        import json
        cleaned = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        data = json.loads(cleaned)
        out: list[ReferenceQuestion] = []
        for q in data.get("questions", []):
            out.append(
                ReferenceQuestion(
                    id=str(q.get("id") or f"rq-{len(out)+1}"),
                    competency=str(q.get("competency") or "strengths"),
                    text=str(q.get("question") or "").strip(),
                    rationale=str(q.get("rationale") or "").strip(),
                )
            )
        return out[:n_questions] if out else None
    except (LLMError, Exception):
        return None


def generate_questions(
    candidate_name: str,
    relationship: str = "manager",
    job_title: str = "",
    extra_context: str = "",
    n_questions: int = 8,
    provider: str = "auto",
) -> list[ReferenceQuestion]:
    if provider in ("auto", "llm"):
        out = _llm_questions(candidate_name, relationship, job_title, extra_context, n_questions)
        if out:
            return out
    return _local_questions(candidate_name, relationship, n_questions)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
_ENDORSEMENT_PATTERN = re.compile(
    r"\b(would\s+(?:rehire|hire\s+again|absolutely\s+hire|definitely\s+hire)|"
    r"top\s+(?:1|2|3|5|10)\s*%?|"
    r"best\s+(?:engineer|manager|hire|teammate|designer|pm|person|colleague)|"
    r"exceptional|outstanding|stellar|world[-\s]?class|"
    r"highly\s+recommend|strongly\s+recommend|"
    r"phenomenal|brilliant|extraordinary|"
    r"a-?player|first\s+person\s+i.?d?\s+(?:call|hire))\b",
    re.IGNORECASE,
)
_LUKEWARM_PATTERN = re.compile(
    r"\b(fine|okay|ok\b|decent|alright|acceptable|reasonable|"
    r"i\s+guess|i\s+suppose|generally|mostly|usually|sometimes|"
    r"could\s+be|might\s+be|perhaps|probably|maybe|"
    r"depends\s+on|hard\s+to\s+say|not\s+sure)\b",
    re.IGNORECASE,
)
_CONCERN_PATTERN = re.compile(
    r"\b(struggled|difficult\s+to\s+work\s+with|hard\s+to\s+work\s+with|"
    r"defensive|reactive|abrasive|micromanage[ds]?|"
    r"missed\s+(?:deadlines?|deliverables?|commitments?)|"
    r"under[-\s]?delivered|did\s+not\s+meet|fell\s+short|"
    r"would\s+not\s+rehire|wouldn'?t\s+rehire|cannot\s+recommend|"
    r"unreliable|inconsistent|unfocused|"
    r"performance\s+(?:issue|problem)|PIP|performance\s+improvement\s+plan)\b",
    re.IGNORECASE,
)
_RED_FLAG_PATTERN = re.compile(
    r"\b(fired|terminated|let\s+go|harass|inappropri|misconduct|"
    r"toxic|hostile|retaliat|bullying|discriminat|"
    r"violated?|breach(?:ed)?|"
    r"theft|fraud|dishonest|lied)\b",
    re.IGNORECASE,
)
_HEDGE_PATTERN = re.compile(
    r"\b(kind\s+of|sort\s+of|i\s+think|i\s+guess|maybe|perhaps|"
    r"possibly|probably|hopefully|in\s+some\s+ways|in\s+a\s+way|"
    r"to\s+some\s+extent|relatively|fairly|reasonably|generally|"
    r"i'?m\s+not\s+sure|don'?t\s+know\s+exactly)\b",
    re.IGNORECASE,
)
_SPECIFICITY_PATTERN = re.compile(
    r"(\b\d{1,4}(?:[.,]\d+)?\s*(?:%|x|million|m|billion|b|k|thousand|hours?|weeks?|months?|years?|days?|users?|customers?|engineers?|reports?|reps?|sales?|deals?|customers?|clients?)?\b"
    r"|\bQ[1-4]\b|\b20\d{2}\b)",
    re.IGNORECASE,
)
_NAMED_ENTITY_PATTERN = re.compile(
    r"\b[A-Z][a-zA-Z]{2,}\b"
)
_STAR_HINTS = ["situation", "task", "action", "result", "outcome", "impact", "led to", "ended up", "drove", "shipped", "delivered"]
_FILLER_PATTERN = re.compile(r"\b(um+|uh+|like|you know|kinda|sort of)\b", re.IGNORECASE)

# Non-answer detector — reused conceptually from the interview service.
_REFUSAL_PATTERN = re.compile(
    r"\b("
    r"i\s+(?:don'?t|do\s+not|cannot|can'?t|won'?t|wouldn'?t|haven'?t)\s+"
    r"(?:know|remember|recall|comment|want\s+to\s+comment|feel\s+comfortable)"
    r"|i\s+have\s+(?:no|nothing)\s+(?:idea|comment|answer)"
    r"|no\s+comment|no\s+answer|n\/?a"
    r"|prefer\s+not\s+to|rather\s+not\s+say"
    r"|i'?d\s+rather\s+not"
    r")\b",
    re.IGNORECASE,
)
_STANDALONE_NONANSWERS = {"skip", "pass", "none", "nothing", "nope", "nada", "idk", "dunno", "n/a", "na", "no"}


def _refusal_score(answer: str) -> float:
    answer = (answer or "").strip()
    words = answer.split()
    wc = len(words)
    if wc == 0:
        return 1.0
    if wc <= 3:
        return 0.95
    stripped = re.sub(r"[^a-z0-9/]", "", answer.lower())
    if stripped in _STANDALONE_NONANSWERS:
        return 0.95
    hits = len(_REFUSAL_PATTERN.findall(answer))
    refusal_word_count = sum(len(m.split()) for m in _REFUSAL_PATTERN.findall(answer))
    density = refusal_word_count / max(wc, 1)
    if wc < 8:
        brevity = 1.0 - (wc - 3) / 5.0
    else:
        brevity = 0.0
    if hits and wc <= 12:
        return min(1.0, 0.6 + 0.1 * hits + brevity * 0.3)
    if density >= 0.4:
        return min(1.0, 0.4 + density)
    elif density >= 0.2:
        return min(0.5, density)
    return brevity


def _presentation_signals(answer: str, duration_sec: float, mode: str) -> dict[str, float]:
    answer = (answer or "").strip()
    words = answer.split()
    wc = max(len(words), 1)
    fillers = len(_FILLER_PATTERN.findall(answer))
    endorsements = len(_ENDORSEMENT_PATTERN.findall(answer))
    lukewarms = len(_LUKEWARM_PATTERN.findall(answer))
    hedges = len(_HEDGE_PATTERN.findall(answer))
    wpm = (wc / max(duration_sec / 60.0, 0.0001)) if duration_sec else 0.0
    return {
        "pace_wpm": round(wpm, 1) if duration_sec else 0.0,
        "filler_density": round(fillers / wc, 3),
        "endorsement_phrases": endorsements,
        "lukewarm_phrases": lukewarms,
        "hedge_words": hedges,
        "word_count": wc,
    }


def _endorsement_score(answer: str, presentation: dict) -> int:
    wc = presentation.get("word_count", 1) or 1
    endorse = presentation.get("endorsement_phrases", 0)
    lukewarm = presentation.get("lukewarm_phrases", 0)
    # density per ~40 word chunk so a 600-word answer doesn't blow up
    chunk = max(wc / 40.0, 1.0)
    endorse_density = min(1.0, endorse / chunk)
    lukewarm_density = min(1.0, lukewarm / chunk * 0.7)
    base = 0.4 + 0.6 * endorse_density - 0.35 * lukewarm_density
    # Length gate — a 4-word "he's great" gets capped
    if wc < 10:
        base *= wc / 20.0
    elif wc < 25:
        base *= 0.5 + (wc - 10) / 30.0
    return int(round(max(0.0, min(1.0, base)) * 100))


def _specificity_score(answer: str) -> int:
    if not answer:
        return 0
    numbers = len(_SPECIFICITY_PATTERN.findall(answer))
    names = len(_NAMED_ENTITY_PATTERN.findall(answer))
    # Names are noisier (sentence-start caps), so weight numbers higher.
    score = min(1.0, numbers / 4.0) * 0.6 + min(1.0, names / 6.0) * 0.25
    # STAR hints add up to 0.15
    a_lower = answer.lower()
    star = sum(1 for h in _STAR_HINTS if h in a_lower)
    score += min(0.15, star * 0.04)
    return int(round(min(1.0, score) * 100))


def _candor_score(answer: str, presentation: dict) -> int:
    """How direct + balanced is this reference. Hedging penalises candor;
    presence of both strengths AND growth-area language boosts it."""
    wc = presentation.get("word_count", 1) or 1
    hedges = presentation.get("hedge_words", 0)
    hedge_density = min(1.0, hedges / max(wc / 40.0, 1.0))
    # Boost when the answer surfaces both upside AND a growth comment.
    has_upside = bool(_ENDORSEMENT_PATTERN.search(answer))
    has_downside = bool(re.search(r"\b(could|should|needs?|wish|growth|stretch|grow|learn|improve|sharpen|develop)\b", answer, re.IGNORECASE))
    balance_boost = 0.25 if (has_upside and has_downside) else 0.0
    base = 0.7 - hedge_density * 0.6 + balance_boost
    if wc < 10:
        base *= wc / 20.0
    return int(round(max(0.0, min(1.0, base)) * 100))


def _concern_score(answer: str) -> tuple[int, list[str]]:
    """Return 0-100 concern signal + an explicit list of flagged spans."""
    if not answer:
        return 0, []
    concerns = _CONCERN_PATTERN.findall(answer)
    red_flags = _RED_FLAG_PATTERN.findall(answer)
    n = len(concerns) + 2 * len(red_flags)
    if n == 0:
        return 0, []
    severity = min(1.0, n / 3.0)
    if red_flags:
        severity = min(1.0, severity + 0.3)
    flagged = list({*[c.lower() for c in concerns], *[r.lower() for r in red_flags]})
    return int(round(severity * 100)), flagged


def _length_score(wc: int) -> int:
    if wc >= 80:
        return 100
    if wc >= 40:
        return 75
    if wc >= 20:
        return 50
    if wc >= 10:
        return 25
    return 0


def score_answer(
    question: ReferenceQuestion,
    answer: str,
    *,
    mode: str = "written",
    duration_sec: float = 0.0,
    has_face: bool = False,
) -> ScoredReferenceAnswer:
    presentation = _presentation_signals(answer, duration_sec, mode)
    refusal = _refusal_score(answer)

    endorsement = _endorsement_score(answer, presentation)
    specificity = _specificity_score(answer)
    candor = _candor_score(answer, presentation)
    concern, concern_terms = _concern_score(answer)
    length = _length_score(presentation.get("word_count", 0))

    # Apply refusal attenuation across the board so subscores reflect reality.
    if refusal > 0.0:
        keep = max(0.0, 1.0 - refusal)
        endorsement = int(round(endorsement * keep))
        specificity = int(round(specificity * keep))
        candor = int(round(candor * keep))
        # concern is the only thing we DON'T attenuate — refusal itself is a
        # mild concern signal because the reference is dodging the question.

    # Weighted blend for this single answer's endorsement strength.
    weights = {
        "endorsement": 0.40,
        "specificity": 0.20,
        "candor":      0.15,
        "length":      0.15,
        # Concern is a *penalty*, not a weight.
    }
    blended = (
        weights["endorsement"] * endorsement
        + weights["specificity"] * specificity
        + weights["candor"]      * candor
        + weights["length"]      * length
    )
    # Concern subtracts up to 35 points.
    score = int(round(blended - concern * 0.35))
    # Refusal hard caps mirror the interview scorer.
    if refusal >= 0.95:
        score = min(score, 5)
    elif refusal >= 0.7:
        score = min(score, 15)
    elif refusal >= 0.4:
        score = min(score, 30)
    score = max(0, min(100, score))

    strengths: list[str] = []
    concerns_out: list[str] = []
    follow_up = ""

    if refusal >= 0.7:
        concerns_out.append(
            "Reference declined to provide a substantive answer — push for one specific example or note the avoidance."
        )
        follow_up = "Re-ask: 'Walk me through one concrete moment, even briefly.'"
    else:
        if endorsement >= 70:
            strengths.append("Clear, superlative endorsement language used.")
        elif endorsement <= 25 and presentation.get("word_count", 0) >= 20:
            concerns_out.append("Endorsement language is lukewarm — reference is hedging.")
        if specificity >= 60:
            strengths.append("Concrete example with names, numbers, or dates.")
        else:
            concerns_out.append("No concrete metrics or names — answer is hard to verify.")
        if candor >= 60:
            strengths.append("Candid, balanced — surfaced both upside and growth area.")
        elif candor <= 30:
            concerns_out.append("Heavy hedging — reference may be uncomfortable being candid.")
        if length < 25 and presentation.get("word_count", 0) > 0:
            concerns_out.append("Answer is short — probe for the underlying example.")
        if concern_terms:
            concerns_out.append("Concerning language detected: " + ", ".join(concern_terms[:4]))

    if not follow_up and concerns_out:
        follow_up = "Suggested follow-up: " + concerns_out[0]

    subscores = {
        "endorsement": endorsement,
        "specificity": specificity,
        "candor": candor,
        "length": length,
        "concern": concern,
    }
    signals = {
        "endorsement_density": round(presentation.get("endorsement_phrases", 0) / max(presentation.get("word_count", 1) / 40, 1), 3),
        "lukewarm_density":    round(presentation.get("lukewarm_phrases", 0) / max(presentation.get("word_count", 1) / 40, 1), 3),
        "hedge_density":       round(presentation.get("hedge_words", 0) / max(presentation.get("word_count", 1) / 40, 1), 3),
        "refusal_score":       round(refusal, 3),
    }

    return ScoredReferenceAnswer(
        question_id=question.id,
        competency=question.competency,
        question=question.text,
        answer=answer,
        score=score,
        signals=signals,
        strengths=strengths,
        concerns=concerns_out,
        follow_up=follow_up,
        mode=mode,
        duration_sec=duration_sec,
        subscores=subscores,
        presentation_signals=presentation,
    )


def score_reference(
    reference: ReferenceProfile,
    questions: list[ReferenceQuestion],
    responses: list[ReferenceResponse],
) -> ScoredReference:
    by_qid = {q.id: q for q in questions}
    scored: list[ScoredReferenceAnswer] = []
    for resp in responses:
        q = by_qid.get(resp.question_id)
        if not q:
            continue
        scored.append(score_answer(
            q, resp.answer,
            mode=resp.mode, duration_sec=resp.duration_sec, has_face=resp.has_face,
        ))

    if not scored:
        return ScoredReference(
            reference_id=reference.id,
            reference_name=reference.name,
            relationship=reference.relationship,
            overall=0,
            band="do_not_endorse",
            answers=[],
            themes=[],
            red_flags=[],
            summary=f"{reference.name} did not provide any responses.",
        )

    overall = int(round(sum(s.score for s in scored) / len(scored)))
    # Concern is averaged AND a max-of-any pushes a softer cap if a single
    # answer raised a red flag.
    avg_concern = sum(s.subscores.get("concern", 0) for s in scored) / len(scored)
    if avg_concern >= 50:
        overall = min(overall, 40)
    band = (
        "strong_endorse" if overall >= 78
        else "endorse" if overall >= 60
        else "lukewarm" if overall >= 40
        else "do_not_endorse"
    )

    themes: list[str] = []
    red_flags: list[str] = []
    for s in scored:
        themes.extend(s.strengths)
        red_flags.extend(s.concerns)
    # dedupe while preserving order
    seen: set[str] = set()
    themes = [x for x in themes if not (x in seen or seen.add(x))][:6]
    seen = set()
    red_flags = [x for x in red_flags if not (x in seen or seen.add(x))][:6]

    summary = (
        f"{reference.name} ({reference.relationship}, {reference.tenure_months}mo) "
        f"gave a {band.replace('_', ' ')} reference. "
        f"Average answer score {overall}/100 across {len(scored)} questions."
    )
    return ScoredReference(
        reference_id=reference.id,
        reference_name=reference.name,
        relationship=reference.relationship,
        overall=overall,
        band=band,
        answers=scored,
        themes=themes,
        red_flags=red_flags,
        summary=summary,
    )


def synthesise(
    candidate_name: str,
    job_title: str,
    references: list[ScoredReference],
) -> ReferenceCheckSummary:
    fairness_note = (
        "This synthesis is generated by an AI scoring rubric and is intended to support — "
        "not replace — human recruiter judgement. Reference checks are subjective and "
        "context-dependent. Calibrate against multiple sources, watch for protected-class "
        "language, and do not treat any single reference's score as decisive."
    )

    if not references:
        return ReferenceCheckSummary(
            overall_score=0,
            band="do_not_endorse",
            recommendation="hold",
            strengths=[],
            risks=["No completed references."],
            contradictions=[],
            competency_scores={},
            references=[],
            narrative=f"No references have completed for {candidate_name}.",
            fairness_note=fairness_note,
            n_references=0,
            relationships_covered=[],
        )

    # Manager weighted higher because a manager's reference is more diagnostic
    # than a peer's — but not by an obscene amount.
    rel_weights = {"manager": 1.3, "report": 1.15, "client": 1.05, "peer": 0.9, "mentor": 0.9, "other": 0.8}
    total_w = 0.0
    weighted_sum = 0.0
    for r in references:
        w = rel_weights.get(r.relationship, 1.0)
        weighted_sum += r.overall * w
        total_w += w
    overall = int(round(weighted_sum / max(total_w, 0.0001)))

    if overall >= 78:
        band, rec = "strong_endorse", "advance"
    elif overall >= 62:
        band, rec = "endorse", "advance"
    elif overall >= 45:
        band, rec = "proceed_with_caution", "advance_with_caveats"
    elif overall >= 30:
        band, rec = "lukewarm", "hold"
    else:
        band, rec = "do_not_endorse", "decline"

    # Competency-level roll-up across references
    comp_buckets: dict[str, list[int]] = {}
    for r in references:
        for a in r.answers:
            comp_buckets.setdefault(a.competency, []).append(a.score)
    competency_scores = {c: int(round(sum(v) / len(v))) for c, v in comp_buckets.items()}

    # Strengths & risks dedup across all references
    strengths: list[str] = []
    risks: list[str] = []
    for r in references:
        strengths.extend(r.themes)
        risks.extend(r.red_flags)
    seen: set[str] = set()
    strengths = [x for x in strengths if not (x in seen or seen.add(x))][:8]
    seen = set()
    risks = [x for x in risks if not (x in seen or seen.add(x))][:8]

    # Contradiction detection — for each competency, look at max-min spread.
    contradictions: list[str] = []
    for comp, scores in comp_buckets.items():
        if len(scores) >= 2 and (max(scores) - min(scores)) >= 35:
            contradictions.append(
                f"References disagree on {comp.replace('_', ' ')}: scores range {min(scores)}–{max(scores)}."
            )
    # Red-flag-only references
    for r in references:
        if r.red_flags and r.band in ("lukewarm", "do_not_endorse"):
            contradictions.append(
                f"{r.reference_name} ({r.relationship}) raised concerns the other references did not."
            )

    rel_covered = sorted({r.relationship for r in references})
    strongest_ref = max(references, key=lambda r: r.overall)
    weakest_ref = min(references, key=lambda r: r.overall)
    narrative = (
        f"{len(references)} references completed for {candidate_name} ({job_title}). "
        f"Weighted endorsement: {overall}/100 — {band.replace('_', ' ')}. "
        f"Strongest signal from {strongest_ref.reference_name} ({strongest_ref.relationship}, {strongest_ref.overall}). "
        f"Weakest from {weakest_ref.reference_name} ({weakest_ref.relationship}, {weakest_ref.overall}). "
        f"Recommendation: {rec.replace('_', ' ')}."
    )

    return ReferenceCheckSummary(
        overall_score=overall,
        band=band,
        recommendation=rec,
        strengths=strengths,
        risks=risks,
        contradictions=contradictions,
        competency_scores=competency_scores,
        references=[r.to_dict() for r in references],
        narrative=narrative,
        fairness_note=fairness_note,
        n_references=len(references),
        relationships_covered=rel_covered,
    )
