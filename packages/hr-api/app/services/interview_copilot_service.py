"""Interview Copilot service — the brain behind the live AI panel.

Operates in three phases, exactly as the product spec calls for:

  BEFORE
    - generate_interview_plan(job, candidate)
    - generate_candidate_specific_questions(job, candidate, scorecard)

  DURING
    - summarise_live_answer(transcript_window)
    - suggest_follow_up_questions(latest_answer, competency, asked_already)
    - map_answer_to_scorecard(latest_answer, scorecard)
    - detect_missing_evidence(scorecard, transcript)
    - real_time_insights(state)   # one call surfaces everything the panel needs

  AFTER
    - generate_post_interview_summary(...)  (delegated to summary service)

The service is **provider-agnostic**: it tries the configured LLM first
and falls back to a calibrated heuristic that produces useful output even
when no LLM is wired. That fallback is documented inline so a reviewer
can tell exactly what is generated vs. retrieved.

Ethical posture:
  - All copilot assistance is *for the interviewer*. There is no candidate-
    side answer generation. The candidate-prep helpers (mock interviews,
    STAR coaching) live in a clearly-separated namespace.
  - Every AI suggestion carries an evidence pointer or "no_evidence" tag.
"""
from __future__ import annotations

import re
import textwrap
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services.interview_transcription_service import full_transcript, list_lines

try:
    from app.services.llm import llm_complete  # type: ignore
except Exception:
    llm_complete = None  # type: ignore


# ---------------------------------------------------------------------------
# Domain dataclasses (mirror spec)
# ---------------------------------------------------------------------------
@dataclass
class Interview:
    id: str
    org_id: str
    candidate_id: Optional[str]
    candidate_name: str
    job_id: Optional[str]
    job_title: str
    interview_type: str       # screen | technical | onsite | culture | final
    scheduled_at: Optional[str]
    duration_minutes: int = 60
    status: str = "scheduled"  # scheduled | live | completed | cancelled
    consent_status: str = "not_collected"
    recording_enabled: bool = False
    interview_plan: Optional[dict] = None
    questions: list[dict] = field(default_factory=list)
    insights: list[dict] = field(default_factory=list)
    participants: list[dict] = field(default_factory=list)  # role / name / status
    created_by: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class InterviewQuestion:
    id: str
    interview_id: str
    text: str
    competency: str
    required: bool
    asked: bool = False
    generated_by_ai: bool = False
    rationale: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class InterviewInsight:
    id: str
    interview_id: str
    type: str           # follow_up | missing_evidence | strong_signal | fairness | summary
    severity: str       # info | warn | block
    title: str
    description: str
    evidence: list[str] = field(default_factory=list)
    recommended_action: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# In-process stores
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_interviews: dict[str, dict[str, Interview]] = {}                 # org_id → id → Interview
_questions: dict[str, list[InterviewQuestion]] = {}               # interview_id → questions
_insights: dict[str, list[InterviewInsight]] = {}                 # interview_id → insights


# ---------------------------------------------------------------------------
# Interview CRUD
# ---------------------------------------------------------------------------
def create_interview(
    *,
    org_id: str,
    candidate_name: str,
    candidate_id: Optional[str],
    job_title: str,
    job_id: Optional[str],
    interview_type: str = "screen",
    duration_minutes: int = 60,
    scheduled_at: Optional[str] = None,
    participants: Optional[list[dict]] = None,
    created_by: Optional[str] = None,
) -> Interview:
    iv = Interview(
        id=str(uuid.uuid4()),
        org_id=org_id,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        job_id=job_id,
        job_title=job_title,
        interview_type=interview_type,
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes,
        participants=participants or [],
        created_by=created_by,
    )
    with _lock:
        _interviews.setdefault(org_id, {})[iv.id] = iv
    return iv


def list_interviews(org_id: str) -> list[Interview]:
    with _lock:
        items = list(_interviews.get(org_id, {}).values())
    items.sort(key=lambda i: i.created_at, reverse=True)
    return items


def get_interview(org_id: str, interview_id: str) -> Optional[Interview]:
    with _lock:
        return _interviews.get(org_id, {}).get(interview_id)


def update_interview(org_id: str, interview_id: str, fields: dict) -> Optional[Interview]:
    with _lock:
        iv = _interviews.get(org_id, {}).get(interview_id)
        if not iv:
            return None
        for k, v in fields.items():
            if hasattr(iv, k):
                setattr(iv, k, v)
        return iv


# ---------------------------------------------------------------------------
# BEFORE phase
# ---------------------------------------------------------------------------
_COMPETENCY_BANK = {
    "screen":    ["communication", "motivation", "role_fit", "logistics"],
    "technical": ["technical_depth", "problem_solving", "code_quality", "system_design"],
    "onsite":    ["technical_depth", "collaboration", "ownership", "communication"],
    "culture":   ["values_alignment", "team_fit", "self_awareness", "feedback"],
    "final":     ["scope", "judgment", "long_term_fit", "compensation_alignment"],
}

# ---------------------------------------------------------------------------
# Which competencies belong to which kind of work
# ---------------------------------------------------------------------------
#
# _COMPETENCY_BANK below is keyed by INTERVIEW TYPE alone, and the job title was
# never consulted. So every onsite interview probed technical_depth,
# collaboration, ownership and communication, and the first question asked was
#
#     "Describe a system you owned end-to-end. Where did you make a non-obvious
#      trade-off?"
#
# A CDL driver interviewing for a regional reefer run was asked that. So would
# an accountant, a dispatcher and a freight broker. Nothing about reefer units,
# hours of service, detention, the monthly close or carrier vetting could ever
# appear, because those competencies did not exist.
#
# Personalisation that is really a software-interview template is worse than an
# obviously generic interview: the candidate can tell we did not read the role,
# and the recruiter gets evidence about competencies the job does not need.
#
# So: the ROLE selects the competencies; the interview type selects how deep to
# go into them. A role we cannot classify gets the universal set — never the
# software set, because "unknown" must not silently mean "engineer".

_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "driving":   ("driver", "cdl", "trucking", "reefer", "flatbed", "otr",
                  "owner-operator", "haul"),
    "dispatch":  ("dispatcher", "dispatch", "fleet coordinator", "load planner"),
    "brokerage": ("broker", "3pl", "freight agent", "carrier sales",
                  "logistics account"),
    "accounting": ("accountant", "accounting", "controller", "bookkeeper",
                   "audit", "financial analyst", "fp&a", "revenue analyst"),
    "software":  ("engineer", "developer", "programmer", "sre", "devops",
                  "architect", "data scientist", "platform"),
    "recruiting": ("recruiter", "talent acquisition", "sourcer"),
    "sales":     ("sales", "account executive", "business development"),
}

# Competencies that apply to anyone doing any job. These are the fallback, and
# they are deliberately free of domain vocabulary.
_UNIVERSAL = ("communication", "ownership", "problem_solving", "motivation")

_ROLE_COMPETENCIES: dict[str, tuple[str, ...]] = {
    "driving": ("equipment_experience", "route_and_schedule", "safety_judgement",
                "dispatch_communication", "breakdown_and_exception",
                "customer_delivery", "ownership"),
    "dispatch": ("prioritisation", "driver_availability", "service_recovery",
                 "dispatch_communication", "cost_service_tradeoff", "ownership"),
    "brokerage": ("carrier_sourcing", "carrier_qualification", "rate_negotiation",
                  "margin_management", "service_failure", "shipper_development"),
    "accounting": ("close_process", "reconciliations", "accruals_and_cutoff",
                   "revenue_recognition", "controls_and_audit",
                   "variance_investigation", "accounting_systems",
                   "accounting_judgement", "ownership"),
    "software": ("technical_depth", "system_design", "code_quality",
                 "problem_solving", "collaboration", "ownership"),
    "recruiting": ("communication", "stakeholder_management", "ownership",
                   "problem_solving"),
    "sales": ("communication", "objection_handling", "ownership", "motivation"),
}


def role_family(job_title: str | None) -> str | None:
    """Which kind of work this title describes, or None if we cannot tell."""
    t = (job_title or "").lower()
    if not t.strip():
        return None
    for family, words in _ROLE_KEYWORDS.items():
        if any(w in t for w in words):
            return family
    return None


def competencies_for(interview_type: str, job_title: str | None = None) -> list[str]:
    """The competencies to probe, chosen by ROLE and shaped by interview type.

    An unclassified role gets the universal set. It is better to ask a driver
    four honest general questions than four questions about system design.
    """
    family = role_family(job_title)
    pool = list(_ROLE_COMPETENCIES.get(family, _UNIVERSAL)) if family else list(_UNIVERSAL)

    # A screen is short and covers fit; a final is about scope and judgement.
    # Both still draw from the role's own competencies.
    if interview_type == "screen":
        return (["motivation", "role_fit"] + pool)[:4]
    if interview_type == "final":
        return (pool[:2] + ["judgment", "long_term_fit"])[:4]
    if interview_type == "culture":
        return ["values_alignment", "team_fit", "self_awareness", "feedback"]
    # Six, not five. The agenda gives 35 minutes to competency probes, which is
    # roughly six at six minutes each -- and a five-way slice cut the driving
    # role's customer_delivery, the competency that covers detention, missed
    # appointments and refused loads. Those are the deliveries a recruiter most
    # wants to hear about.
    return pool[:6]


_LOCAL_QUESTION_TEMPLATES = {
    "communication":     ["Walk me through a complex decision you had to explain to a non-technical stakeholder."],
    "motivation":        ["Why this role, and why now? What would have to be true at month 6 for you to feel this was a great move?"],
    "role_fit":          ["What part of the {job} role excites you most, and what part are you least certain about?"],
    "logistics":         ["What's your timeline + start-date flexibility?"],
    "technical_depth":   ["Describe a system you owned end-to-end. Where did you make a non-obvious trade-off?"],
    "problem_solving":   ["Tell me about a time the obvious solution wasn't the right one. What did you see that others missed?"],
    "code_quality":      ["How do you decide when code is 'done enough'? Concrete example, please."],
    "system_design":     ["Sketch the architecture you'd propose for {job} day-1. What would you defer to day-90?"],
    "collaboration":     ["Tell me about a real disagreement with a peer. How did it resolve?"],
    "ownership":         ["What's an outcome you owned where nobody told you it was your job?"],
    "values_alignment":  ["When have you pushed back on a leader because their direction conflicted with your values?"],
    "team_fit":          ["What do you need from a manager / team to do your best work?"],
    "self_awareness":    ["What's the most useful piece of feedback you ever received? What did you change?"],
    "feedback":          ["Tell me about a time you gave hard feedback. How did you frame it?"],
    "scope":             ["What's the largest scope you've owned end-to-end, in scope and dollars?"],
    "judgment":          ["Describe a high-stakes trade-off where you had limited information. How did you decide?"],
    "long_term_fit":     ["What does the next 3 years look like for you? Where does this role land in that?"],
    "compensation_alignment": ["What expectations do you have on compensation structure (base / equity / variable)?"],

    # --- driving ---------------------------------------------------------
    "equipment_experience": [
        "What equipment have you run most recently, and what were you hauling? "
        "Walk me through a load where the equipment itself gave you trouble."],
    "route_and_schedule": [
        "Tell me about your typical week — OTR, regional or local? How did you "
        "manage your hours across it?"],
    "safety_judgement": [
        "Describe a time you decided not to drive, or to stop. What made the "
        "call for you, and what happened next?"],
    "dispatch_communication": [
        "Tell me about a run where the plan changed mid-route. How did you and "
        "dispatch work it out?"],
    "breakdown_and_exception": [
        "Walk me through the last breakdown or roadside issue you had. What did "
        "you do in the first hour?"],
    "customer_delivery": [
        "Tell me about a delivery that went badly at the receiver — detention, a "
        "missed appointment, a refused load. How did you handle it?"],

    # --- dispatch --------------------------------------------------------
    "prioritisation": [
        "You have more loads than drivers on a Friday afternoon. Walk me through "
        "how you decide what moves and what does not."],
    "driver_availability": [
        "How do you keep track of who is available, and what do you do when the "
        "driver you planned on is out of hours?"],
    "service_recovery": [
        "Tell me about an appointment you were going to miss. What did you do "
        "before the customer found out?"],
    "cost_service_tradeoff": [
        "Describe a time keeping a customer happy cost the company money. How "
        "did you decide it was worth it?"],

    # --- brokerage / 3PL -------------------------------------------------
    "carrier_sourcing": [
        "Walk me through how you cover a lane you have never run before."],
    "carrier_qualification": [
        "What do you check before you give a carrier a load? Tell me about one "
        "you turned down."],
    "rate_negotiation": [
        "Tell me about a negotiation where the carrier held firm. What did you "
        "do?"],
    "margin_management": [
        "How do you protect margin on a load that is going sideways?"],
    "service_failure": [
        "Describe a service failure you had to tell a shipper about. How did you "
        "open that conversation?"],
    "shipper_development": [
        "How did you win your last new shipper? What did it take?"],

    # --- accounting ------------------------------------------------------
    "close_process": [
        "Walk me through your month-end close. What do you own, and where does "
        "it usually get stuck?"],
    "reconciliations": [
        "Tell me about a reconciliation that would not tie out. How did you find "
        "the difference?"],
    "accruals_and_cutoff": [
        "How do you decide what to accrue at period end when the invoice has not "
        "arrived? Give me a real example."],
    "revenue_recognition": [
        "Describe a revenue recognition question you had to work through. What "
        "made it a judgement call?"],
    "controls_and_audit": [
        "What controls do you own, and what have you had to show an auditor? "
        "Tell me about a request you could not immediately satisfy."],
    "variance_investigation": [
        "Tell me about a variance you investigated that turned out to be real. "
        "How did you track it down, and what did you do about it?"],
    "accounting_systems": [
        "Which ERP or accounting systems have you closed in? What did you have "
        "to work around?"],
    "accounting_judgement": [
        "Tell me about an error you caught before close. How did you find it, "
        "and what did you change afterwards?"],

    # --- general ---------------------------------------------------------
    "stakeholder_management": [
        "Tell me about a stakeholder who wanted something you could not give "
        "them. How did that end?"],
    "objection_handling": [
        "What is the objection you hear most, and how do you actually answer it?"],
}


def generate_interview_plan(
    *,
    interview_type: str,
    job_title: str,
    job_description: str,
    candidate_summary: str,
    extracted_skills: Optional[list[str]] = None,
    skill_gaps: Optional[list[str]] = None,
) -> dict:
    """Synthesise an interview plan: focus areas, agenda, role-specific cues.

    Tries the LLM, falls back to a structured local template that splices
    in candidate-specific gaps and strengths.
    """
    extracted_skills = extracted_skills or []
    skill_gaps = skill_gaps or []
    if llm_complete is not None:
        try:
            prompt = textwrap.dedent(f"""
                Build a structured interview plan.
                Interview type: {interview_type}
                Role: {job_title}
                Job description: {job_description[:1200]}
                Candidate summary: {candidate_summary[:1200]}
                Candidate skills: {', '.join(extracted_skills) or 'unknown'}
                Skill gaps to probe: {', '.join(skill_gaps) or 'none flagged'}

                Return JSON:
                {{
                  "focus_areas": ["..."],
                  "agenda": [{{"minutes": 5, "topic": "..."}}],
                  "verify": ["..."],
                  "concerns_to_explore": ["..."],
                  "positive_signals_to_confirm": ["..."],
                  "candidate_specific_notes": "1-2 sentences."
                }}
            """).strip()
            raw = llm_complete(prompt, system="You are a calibrated structured interviewer.")
            import json
            cleaned = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
            data = json.loads(cleaned)
            data["generated_by"] = "llm"
            return data
        except Exception:
            pass

    # Local fallback — structured + opinionated
    #
    # EVERY LINE BELOW USED TO ASSERT A RESUME. "Resume signals strong on the
    # listed skills", "resume reads strong but generic" — printed verbatim for a
    # candidate with no summary and no skills, because the caller had been
    # passing hard-coded ones. With that removed, an unscreened candidate got a
    # plan confidently describing a resume nobody had read. A plan built on the
    # role alone is a perfectly good plan; claiming to have read a resume is
    # not.
    have_summary = bool((candidate_summary or "").strip())
    # Chosen by ROLE, shaped by interview type. Keyed by interview type
    # alone, this handed a CDL driver "technical_depth" and asked them to
    # describe a system they owned end-to-end.
    focus = competencies_for(interview_type, job_title)
    agenda = [
        {"minutes": 5,  "topic": "Intro + agenda + consent confirmation"},
        {"minutes": 35, "topic": f"Competency probes: {', '.join(focus)}"},
        {"minutes": 10, "topic": ("Candidate-specific deep dive (resume gaps)"
                                  if have_summary else
                                  "Open-ended deep dive — background and scope")},
        {"minutes": 5,  "topic": "Candidate questions"},
        {"minutes": 5,  "topic": "Next steps + close"},
    ]
    verify = [f"Direct experience with {s}" for s in extracted_skills[:3]]
    concerns = [f"Limited evidence of {g}" for g in skill_gaps[:3]]
    if not concerns:
        concerns = [
            "Confirm specific outcomes (numbers, dates, scope) — resume reads "
            "strong but generic."
            if have_summary else
            "Establish specific outcomes (numbers, dates, scope) from scratch — "
            "there is no resume or summary on file to check them against."
        ]
    positives = [
        "Multiple references to ownership language in candidate summary."
        if have_summary and "owned" in candidate_summary.lower() else
        "Confirm whether candidate has direct end-to-end ownership.",
    ]
    cs_note = (
        "Resume signals strong on the listed skills; the plan front-loads "
        "competencies the resume understates."
        if have_summary else
        f"No candidate summary was available, so this plan is built on the "
        f"{job_title or interview_type} role and the interview type alone. "
        f"Screen the candidate to get resume-specific focus areas."
    )

    return {
        "focus_areas": focus,
        "agenda": agenda,
        "verify": verify,
        "concerns_to_explore": concerns,
        "positive_signals_to_confirm": positives,
        "candidate_specific_notes": cs_note,
        "generated_by": "local",
    }


def generate_candidate_specific_questions(
    *,
    interview_id: str,
    interview_type: str,
    job_title: str,
    candidate_summary: str,
    skill_gaps: Optional[list[str]] = None,
    n_questions: int = 7,
) -> list[InterviewQuestion]:
    """Produce a per-interview question list, persist + return."""
    skill_gaps = skill_gaps or []
    competencies = competencies_for(interview_type, job_title)
    questions: list[InterviewQuestion] = []

    # 1. Core competency questions
    for comp in competencies:
        templates = _LOCAL_QUESTION_TEMPLATES.get(comp, [])
        if not templates:
            continue
        text = templates[0].replace("{job}", job_title)
        questions.append(InterviewQuestion(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            text=text,
            competency=comp,
            required=True,
            generated_by_ai=True,
            rationale=f"Core probe for {comp.replace('_', ' ')}.",
        ))

    # 2. Skill-gap probes
    for gap in skill_gaps[:2]:
        questions.append(InterviewQuestion(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            text=f"Your resume doesn't call out {gap}. Walk me through any exposure you have to it and how you'd ramp.",
            competency="technical_depth",
            required=True,
            generated_by_ai=True,
            rationale=f"Resume gap on {gap}.",
        ))

    # 3. Candidate-specific probe
    if "owned" in candidate_summary.lower():
        questions.append(InterviewQuestion(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            text="You mention ownership of multiple workstreams — pick the one that taught you the most, walk me through what you'd do differently.",
            competency="self_awareness",
            required=False,
            generated_by_ai=True,
            rationale="Resume signals strong ownership; probe self-awareness behind it.",
        ))

    out = questions[:n_questions]
    with _lock:
        _questions[interview_id] = out
    return out


def list_questions(interview_id: str) -> list[InterviewQuestion]:
    return list(_questions.get(interview_id, []))


def mark_question_asked(interview_id: str, question_id: str) -> Optional[InterviewQuestion]:
    with _lock:
        for q in _questions.get(interview_id, []):
            if q.id == question_id:
                q.asked = True
                return q
    return None


# ---------------------------------------------------------------------------
# DURING phase — real-time helpers
# ---------------------------------------------------------------------------
def summarise_live_answer(transcript_window: str, *, max_chars: int = 240) -> str:
    """Compress a recent transcript window into a 1-2 sentence summary."""
    text = (transcript_window or "").strip()
    if not text:
        return ""
    if llm_complete is not None:
        try:
            prompt = (
                "Summarise the candidate's answer in 1-2 calm sentences. "
                "Preserve concrete facts (numbers, dates, scope). "
                "No prefix, no quotes.\n\n"
                f"Transcript:\n{text[:3000]}"
            )
            raw = llm_complete(prompt, system="You are a calibrated note-taker.")
            return raw.strip()[:max_chars]
        except Exception:
            pass

    # Local fallback — first 2 sentences, normalise whitespace
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(sentences[:2]).strip()
    return summary[:max_chars]


def suggest_follow_up_questions(
    *,
    latest_answer: str,
    competency: str,
    asked_already: list[str],
    n: int = 3,
) -> list[dict]:
    """Generate 2-3 candidate follow-up questions for the interviewer.

    Returns list of {"text": str, "competency": str, "rationale": str}.
    """
    if llm_complete is not None:
        try:
            prompt = textwrap.dedent(f"""
                The candidate just gave this answer about {competency.replace('_', ' ')}:
                "{latest_answer[:1000]}"

                Already asked: {asked_already[:5]}

                Generate {n} sharp follow-up questions a calibrated interviewer would ask.
                JSON only: [{{"text": "...", "competency": "...", "rationale": "..."}}]
            """).strip()
            raw = llm_complete(prompt, system="You are a calibrated technical interviewer.")
            import json
            cleaned = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
            data = json.loads(cleaned)
            return data[:n]
        except Exception:
            pass

    # Local fallback — heuristic follow-ups
    out: list[dict] = []
    answer_lower = latest_answer.lower()
    # Detect: numbers? specifics? scope?
    has_numbers = bool(re.search(r"\b\d{1,4}\b", latest_answer))
    has_team = bool(re.search(r"\b(team|peer|stakeholder|manager)\b", answer_lower))
    has_outcome = bool(re.search(r"\b(result|outcome|impact|shipped|delivered|launched)\b", answer_lower))

    if not has_numbers:
        out.append({
            "text": "Can you put a number on that — scope, headcount, dollars, anything quantitative?",
            "competency": competency,
            "rationale": "No numerical specificity in the answer.",
        })
    if not has_team:
        out.append({
            "text": "Who else was involved? How did the cross-functional piece work?",
            "competency": "collaboration",
            "rationale": "Answer is solo-flavoured; probe collaboration.",
        })
    if not has_outcome:
        out.append({
            "text": "What was the result? How did you know it worked?",
            "competency": competency,
            "rationale": "No outcome language — probe measurable impact.",
        })
    if len(out) < n:
        out.append({
            "text": "What would you do differently if you ran the same play tomorrow?",
            "competency": "self_awareness",
            "rationale": "Universally useful probe of growth orientation.",
        })
    return out[:n]


def map_answer_to_scorecard(
    *,
    latest_answer: str,
    scorecard_competencies: list[str],
) -> list[dict]:
    """For each scorecard competency, infer how the latest answer maps."""
    answer_lower = (latest_answer or "").lower()
    out: list[dict] = []
    keywords_by_comp = {
        "communication":    ["explained", "presented", "walked through", "summarised"],
        "technical_depth":  ["architecture", "design", "algorithm", "trade-off", "performance"],
        "problem_solving":  ["debugged", "root cause", "investigated", "hypothesis"],
        "ownership":        ["i owned", "i led", "i drove", "i decided", "end-to-end"],
        "collaboration":    ["team", "peer", "stakeholder", "cross-functional"],
        "values_alignment": ["values", "ethics", "right thing", "pushed back"],
        "judgment":         ["trade-off", "weighed", "decided", "evaluated", "chose"],
    }
    for comp in scorecard_competencies:
        kws = keywords_by_comp.get(comp, [])
        hits = [kw for kw in kws if kw in answer_lower]
        evidence = bool(hits)
        out.append({
            "competency": comp,
            "evidence_detected": evidence,
            "matched_phrases": hits[:3],
            "confidence": 0.7 if evidence else 0.2,
            "suggested_rating": 3 if len(hits) >= 2 else 2 if hits else None,
            "note": (
                f"Mapped to {comp} via: {', '.join(hits[:3])}" if hits
                else f"No direct evidence for {comp.replace('_', ' ')} in this answer."
            ),
        })
    return out


def detect_missing_evidence(
    *,
    scorecard_competencies: list[str],
    transcript: str,
) -> list[InterviewInsight]:
    """Surface competencies that have no transcript evidence yet."""
    transcript_lower = (transcript or "").lower()
    out: list[InterviewInsight] = []
    for comp in scorecard_competencies:
        comp_word = comp.replace("_", " ").lower()
        # Heuristic: search for competency word or known proxy words
        proxies = {
            "communication": ["explain", "present", "wrote", "describe"],
            "technical_depth": ["architecture", "system", "design", "algorithm"],
            "problem_solving": ["debug", "root cause", "investigate"],
            "ownership": ["owned", "drove", "decided", "end-to-end"],
            "collaboration": ["team", "peer", "stakeholder"],
            "values_alignment": ["value", "ethic"],
        }.get(comp, [])
        if comp_word in transcript_lower:
            continue
        if any(p in transcript_lower for p in proxies):
            continue
        out.append(InterviewInsight(
            id=str(uuid.uuid4()),
            interview_id="",  # filled by caller
            type="missing_evidence",
            severity="warn",
            title=f"No evidence for {comp.replace('_', ' ')}",
            description=f"The transcript so far doesn't surface anything specific to {comp.replace('_', ' ')}. Consider probing before the interview ends.",
            evidence=[],
            recommended_action=f"Ask a targeted {comp.replace('_', ' ')} question.",
        ))
    return out


def record_insight(interview_id: str, insight: InterviewInsight) -> InterviewInsight:
    insight.interview_id = interview_id
    with _lock:
        _insights.setdefault(interview_id, []).append(insight)
    return insight


def list_insights(interview_id: str) -> list[InterviewInsight]:
    return list(_insights.get(interview_id, []))


# ---------------------------------------------------------------------------
# Single live-context endpoint helper
# ---------------------------------------------------------------------------
def live_context(
    *,
    interview_id: str,
    scorecard_competencies: list[str],
    window_seconds: int = 90,
) -> dict:
    """Compact "everything the panel needs right now" payload.

    Intended for the live copilot UI's right-rail panel.
    """
    transcript = full_transcript(interview_id)
    recent = "\n".join(line.text for line in list_lines(interview_id)[-8:])
    summary = summarise_live_answer(recent)
    missing = detect_missing_evidence(
        scorecard_competencies=scorecard_competencies,
        transcript=transcript,
    )
    mapping = map_answer_to_scorecard(
        latest_answer=recent,
        scorecard_competencies=scorecard_competencies,
    )
    follow_ups = suggest_follow_up_questions(
        latest_answer=recent or transcript,
        competency=(scorecard_competencies[0] if scorecard_competencies else "communication"),
        asked_already=[],
    )
    return {
        "live_summary": summary,
        "missing_evidence": [i.to_dict() for i in missing],
        "scorecard_mapping": mapping,
        "follow_up_questions": follow_ups,
        "transcript_lines": len(list_lines(interview_id)),
    }
