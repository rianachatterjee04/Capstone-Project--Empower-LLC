"""Recruiting Intelligence — the AI brain that turns the recruiting layer
from a static ATS into an operational, agentic surface.

Builds on top of existing primitives without touching them:
  * ``Candidate`` + ``JobPosting`` ORM models
  * ``resume_matching_service`` (skill extraction, semantic match, ranking)
  * ``ai_interview_service`` (interview scoring, summary)
  * ``reference_check_service`` (reference synthesis)

What it adds:
  1. **Stage bottleneck detection** — where candidates are stalling per req.
  2. **AI sourcing** — semantic + skill match a job to your *passive*
     candidate pool (anyone in the org's CRM, not just applicants for that
     specific role).
  3. **AI outreach drafting** — first-touch + follow-up templates that
     splice the candidate's strongest signals into the message.
  4. **Pipeline analytics** — funnel conversion, time-to-fill, source mix,
     recruiter productivity.
  5. **Candidate insights** — adjacent skills inference, career trajectory,
     internal mobility flag.
  6. **Talent pool auto-bucketing** — clusters candidates by dominant
     skills so the recruiter can warm pools instead of every candidate.
  7. **Scorecard rollup** — folds AI interview + reference signals into
     one calibrated debrief per candidate.

Everything here is a pure function or async-DB read. No state. No new
tables — the demo runs against the existing schema. Stubs are clearly
marked so a follow-on can wire real LLM / vector stores.
"""
from __future__ import annotations

import math
import re
import statistics
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Candidate, JobPosting
from app.services.embeddings import embedding
from app.services.resume_matching_service import (
    SkillEvidence,
    extract_skills,
    match_resume,
)

try:
    from app.services.llm import llm_complete  # type: ignore
    from app.services.llm import LLMError  # type: ignore
except Exception:
    llm_complete = None  # type: ignore

    class LLMError(Exception):
        pass


# ---------------------------------------------------------------------------
# Canonical pipeline
# ---------------------------------------------------------------------------
# The product spec calls for: Applied → AI Screened → Recruiter Review →
# Interview → Offer → Hired (+ Rejected sink). We map ``Candidate.status``
# loosely to this; unknown statuses fall back to "applied".
PIPELINE_STAGES = [
    ("applied",          "Applied"),
    ("ai_screened",      "AI Screened"),
    ("recruiter_review", "Recruiter Review"),
    ("interview",        "Interview"),
    ("offer",            "Offer"),
    ("hired",            "Hired"),
]
STAGE_INDEX = {key: i for i, (key, _) in enumerate(PIPELINE_STAGES)}
TERMINAL_STAGES = {"hired", "rejected", "withdrawn"}
# Industry-ish dwell-time targets (days) — easy to tune later.
STAGE_TARGETS = {
    "applied": 1.0,
    "ai_screened": 1.0,
    "recruiter_review": 2.0,
    "interview": 7.0,
    "offer": 3.0,
}


def _stage_key(status: Optional[str]) -> str:
    s = (status or "").strip().lower().replace(" ", "_")
    if not s:
        return "applied"
    if s in STAGE_INDEX:
        return s
    if s in ("new", "submitted", "received"):
        return "applied"
    if s in ("screening", "ai_screen", "auto_screen"):
        return "ai_screened"
    if s in ("review", "shortlist", "shortlisted"):
        return "recruiter_review"
    if s in ("phone_screen", "panel", "onsite", "loop"):
        return "interview"
    if s in ("rejected", "declined", "no_hire"):
        return "rejected"
    if s in ("withdrawn", "ghosted"):
        return "withdrawn"
    if s == "hired":
        return "hired"
    if s == "offer":
        return "offer"
    return "applied"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class BottleneckSignal:
    job_id: str
    job_title: str
    stage: str
    stage_label: str
    candidates_in_stage: int
    avg_days_in_stage: float
    target_days: float
    severity: str            # ok | watch | alert | critical
    note: str

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class FunnelMetrics:
    job_id: str
    job_title: str
    counts: dict[str, int]
    conversion: dict[str, float]   # e.g. "ai_screened->recruiter_review": 0.32
    time_to_first_screen_days: float
    time_to_offer_days: float
    open_days: int

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class SourcingMatch:
    candidate_id: str
    candidate_name: str
    current_job_id: Optional[str]
    current_status: str
    overall_score: float
    skill_overlap: list[str]
    adjacent_skills: list[str]
    evidence_snippets: list[str]
    why_match: str
    last_seen_days: int

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class OutreachDraft:
    candidate_id: str
    candidate_name: str
    job_title: str
    channel: str            # email | linkedin | slack
    tone: str               # warm | direct | warm_referral
    subject: str
    body: str
    rationale: str          # why we drafted it this way
    follow_up_body: str
    is_llm_generated: bool

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class CandidateInsight:
    candidate_id: str
    candidate_name: str
    job_id: Optional[str]
    job_title: Optional[str]
    headline_skills: list[str]
    adjacent_skills: list[str]
    career_trajectory: list[str]   # ordered stages inferred from the resume
    seniority_estimate: str        # IC1-3 / IC4 / IC5+ / mgr / sr_mgr / director / executive
    internal_mobility_flag: bool
    promotion_readiness: float     # 0-1
    summary: str

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class TalentPool:
    id: str
    name: str
    description: str
    candidate_ids: list[str]
    skill_signature: list[str]
    avg_score: float

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class RecruiterProductivity:
    open_reqs: int
    candidates_in_flight: int
    candidates_added_7d: int
    interviews_done_30d: int
    avg_time_to_first_screen_days: float
    avg_time_to_offer_days: float
    bottlenecks_critical: int
    silent_candidates_3d: int      # candidates with no recruiter action in 3d
    notes: list[str]

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class CandidateExperienceSignal:
    candidate_id: str
    candidate_name: str
    stage: str
    days_in_stage: int
    last_touch_days: int
    risk: str                     # ok | delay | ghosted | stalled
    note: str

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ScorecardRollup:
    candidate_id: str
    candidate_name: str
    job_id: Optional[str]
    ai_screen_score: Optional[int]
    interview_overall: Optional[int]
    interview_dimensions: dict[str, int]
    reference_overall: Optional[int]
    reference_band: Optional[str]
    composite_score: int
    recommendation: str           # advance / advance_with_caveats / hold / decline
    strengths: list[str]
    risks: list[str]
    next_actions: list[str]

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _days_between(a: datetime, b: datetime) -> float:
    delta = b - a
    return max(0.0, delta.total_seconds() / 86400.0)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _severity_for_dwell(actual: float, target: float) -> str:
    if actual <= target:
        return "ok"
    if actual <= target * 2:
        return "watch"
    if actual <= target * 4:
        return "alert"
    return "critical"


# ---------------------------------------------------------------------------
# 1. Stage bottleneck detection
# ---------------------------------------------------------------------------
async def detect_bottlenecks(db: AsyncSession, org_id: UUID) -> list[BottleneckSignal]:
    """Group candidates by job × stage and flag where dwell time blows past
    the per-stage target. Severity is logarithmic so a single critical
    bottleneck pops without drowning the recruiter in yellows."""
    jobs = (await db.execute(
        select(JobPosting).where(JobPosting.org_id == org_id, JobPosting.status != "archived")
    )).scalars().all()

    out: list[BottleneckSignal] = []
    now = _now_utc()
    for job in jobs:
        cands = (await db.execute(
            select(Candidate).where(
                Candidate.org_id == org_id,
                Candidate.job_posting_id == job.id,
            )
        )).scalars().all()
        by_stage: dict[str, list[Candidate]] = {}
        for c in cands:
            stage = _stage_key(c.status)
            if stage in TERMINAL_STAGES:
                continue
            by_stage.setdefault(stage, []).append(c)
        for stage, group in by_stage.items():
            target = STAGE_TARGETS.get(stage, 3.0)
            # We don't track stage-entry timestamps in the demo schema, so
            # use ``created_at`` as a proxy for "in the funnel". A real impl
            # would replace this with stage-transition events.
            dwell_days = [_days_between(c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at, now) for c in group]
            avg_dwell = round(sum(dwell_days) / max(len(dwell_days), 1), 1)
            severity = _severity_for_dwell(avg_dwell, target)
            stage_label = dict(PIPELINE_STAGES).get(stage, stage.replace("_", " ").title())
            if severity == "ok":
                note = f"{len(group)} in {stage_label} — pacing fine."
            elif severity == "watch":
                note = f"{len(group)} candidates sitting ~{avg_dwell}d in {stage_label}. Within tolerance but worth a sweep."
            elif severity == "alert":
                note = f"{len(group)} candidates stalled ~{avg_dwell}d in {stage_label} (target {target}d). Recruiter action recommended."
            else:
                note = f"{len(group)} candidates in {stage_label} for ~{avg_dwell}d — {round(avg_dwell / target, 1)}× the target. Pipeline at risk."
            out.append(BottleneckSignal(
                job_id=str(job.id),
                job_title=job.title,
                stage=stage,
                stage_label=stage_label,
                candidates_in_stage=len(group),
                avg_days_in_stage=avg_dwell,
                target_days=target,
                severity=severity,
                note=note,
            ))
    # Sort: critical first, then by dwell time
    severity_order = {"critical": 0, "alert": 1, "watch": 2, "ok": 3}
    out.sort(key=lambda b: (severity_order.get(b.severity, 9), -b.avg_days_in_stage))
    return out


# ---------------------------------------------------------------------------
# 2. AI sourcing — match a job against the org's passive pool
# ---------------------------------------------------------------------------
async def source_for_job(
    db: AsyncSession,
    org_id: UUID,
    job_id: UUID,
    *,
    limit: int = 12,
    include_current_applicants: bool = False,
) -> list[SourcingMatch]:
    """Returns the top passive candidates from the org's CRM whose resume
    semantically + lexically matches the job's description."""
    job = (await db.execute(
        select(JobPosting).where(JobPosting.id == job_id, JobPosting.org_id == org_id)
    )).scalar_one_or_none()
    if not job:
        return []

    job_skills, _ = extract_skills(job.description or "")
    job_emb = embedding(job.description or "")

    cands_q = await db.execute(
        select(Candidate).where(Candidate.org_id == org_id)
    )
    cands = cands_q.scalars().all()

    out: list[SourcingMatch] = []
    now = _now_utc()
    for c in cands:
        if not c.resume_text:
            continue
        # Skip people already on this req unless caller opts in
        if not include_current_applicants and c.job_posting_id == job_id:
            continue
        # Skip terminals
        if _stage_key(c.status) in TERMINAL_STAGES:
            continue
        cand_skills, evidence = extract_skills(c.resume_text)
        overlap = sorted(job_skills & cand_skills)
        adjacent = sorted(cand_skills - job_skills)[:6]
        # Skill score
        denom = max(len(job_skills), 1)
        skill_score = len(overlap) / denom
        # Semantic score
        try:
            cand_emb = embedding(c.resume_text)
            sem = _cosine_safe(job_emb, cand_emb)
        except Exception:
            sem = 0.0
        # Composite
        score = 0.55 * sem + 0.45 * skill_score
        if score < 0.08:
            continue
        snippets: list[str] = []
        for ev in evidence:
            if ev.skill in overlap and ev.snippet:
                snippets.append(f"{ev.skill}: …{ev.snippet}…")
            if len(snippets) >= 3:
                break
        last_seen = int(_days_between(
            c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at,
            now,
        ))
        why = (
            f"{len(overlap)}/{denom} of the required skills match"
            + (f", strongest on {', '.join(overlap[:3])}" if overlap else "")
            + (f". Adjacent strengths: {', '.join(adjacent[:3])}" if adjacent else "")
            + f". Semantic alignment {round(sem * 100)}%."
        )
        out.append(SourcingMatch(
            candidate_id=str(c.id),
            candidate_name=c.full_name,
            current_job_id=str(c.job_posting_id) if c.job_posting_id else None,
            current_status=_stage_key(c.status),
            overall_score=round(score, 3),
            skill_overlap=overlap,
            adjacent_skills=adjacent,
            evidence_snippets=snippets,
            why_match=why,
            last_seen_days=last_seen,
        ))
    out.sort(key=lambda m: -m.overall_score)
    return out[:limit]


def _cosine_safe(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return max(0.0, min(1.0, dot / (na * nb))) if na and nb else 0.0


# ---------------------------------------------------------------------------
# 3. AI outreach drafting
# ---------------------------------------------------------------------------
def draft_outreach(
    *,
    candidate_name: str,
    candidate_id: str,
    job_title: str,
    job_description: str,
    candidate_resume: str = "",
    channel: str = "email",
    tone: str = "warm",
    recruiter_name: str = "the Foundry People recruiting team",
    company_name: str = "our team",
) -> OutreachDraft:
    """Generate a first-touch + follow-up message. Tries the LLM, then
    falls back to a high-quality template that splices in the candidate's
    strongest skills + a teaser of why we're reaching out."""
    channel = (channel or "email").lower()
    tone = (tone or "warm").lower()
    overlap: list[str] = []
    if candidate_resume:
        cand_skills, _ = extract_skills(candidate_resume)
        job_skills, _ = extract_skills(job_description)
        overlap = sorted(cand_skills & job_skills)[:3]

    # Try LLM first
    if llm_complete is not None:
        try:
            prompt = textwrap.dedent(f"""
                Draft a short, calm, modern recruiting outreach message and a
                follow-up. Tone: {tone}. Channel: {channel}.

                Candidate name: {candidate_name}
                Role: {job_title}
                Company: {company_name}
                Recruiter name: {recruiter_name}
                Strongest matching skills: {', '.join(overlap) or 'general profile match'}

                Constraints:
                  - First message: max 100 words.
                  - Subject line: max 60 chars, no spam phrases.
                  - Reference one specific reason why we reached out.
                  - Follow-up: max 60 words.
                  - Tone is human, never bro-y, never desperate.
                  - No generic openers ("hope this finds you well").

                Return JSON: {{"subject": "...", "body": "...", "follow_up": "...", "rationale": "..."}}.
            """).strip()
            raw = llm_complete(prompt, system="You are a calibrated technical recruiter.")
            import json
            cleaned = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
            data = json.loads(cleaned)
            return OutreachDraft(
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                job_title=job_title,
                channel=channel,
                tone=tone,
                subject=str(data.get("subject") or f"{candidate_name.split()[0]} — quick thought on {job_title}")[:80],
                body=str(data.get("body") or "").strip(),
                follow_up_body=str(data.get("follow_up") or "").strip(),
                rationale=str(data.get("rationale") or "").strip(),
                is_llm_generated=True,
            )
        except (LLMError, Exception):
            pass

    # Local fallback — calm, modern, splices in candidate signal
    first = candidate_name.split()[0] if candidate_name else "there"
    why_line = ""
    if overlap:
        why_line = f"Your work on {', '.join(overlap)} is exactly the kind of profile we're looking for."
    else:
        why_line = "Your background looked like a strong fit for the work the team is doing right now."

    tone_lead = {
        "warm":          f"Hi {first} — I came across your profile and wanted to reach out directly.",
        "direct":        f"{first}, short note from {recruiter_name}.",
        "warm_referral": f"Hi {first} — your name came up in a conversation about a role we're hiring for at {company_name}.",
    }.get(tone, f"Hi {first} —")

    subject_tpl = {
        "warm":   f"{first} — quick thought on a {job_title} role",
        "direct": f"{job_title} role at {company_name}",
        "warm_referral": f"{first} — {job_title} role (warm intro)",
    }.get(tone, f"{first} — {job_title} role")

    body = textwrap.dedent(f"""
        {tone_lead}

        We're hiring a {job_title} at {company_name}. {why_line}

        I'd love 15 minutes to share what the team is working on and hear what you're thinking about for what's next. No expectation — just a low-pressure conversation.

        — {recruiter_name}
    """).strip()

    follow_up = textwrap.dedent(f"""
        {first}, circling back on the {job_title} role at {company_name}. Totally understand if the timing isn't right — happy to stay in touch and revisit later. Are you open to a quick chat in the next two weeks?
    """).strip()

    rationale = (
        f"Tone={tone}, channel={channel}. "
        + (f"Splice on overlapping skills: {', '.join(overlap)}." if overlap else "No skill overlap detected; using profile-fit framing.")
    )

    return OutreachDraft(
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        job_title=job_title,
        channel=channel,
        tone=tone,
        subject=subject_tpl[:80],
        body=body,
        follow_up_body=follow_up,
        rationale=rationale,
        is_llm_generated=False,
    )


# ---------------------------------------------------------------------------
# 4. Pipeline analytics — per-job funnel + time-to-fill
# ---------------------------------------------------------------------------
async def funnel_metrics(db: AsyncSession, org_id: UUID) -> list[FunnelMetrics]:
    jobs = (await db.execute(
        select(JobPosting).where(JobPosting.org_id == org_id)
    )).scalars().all()
    out: list[FunnelMetrics] = []
    now = _now_utc()
    for job in jobs:
        cands = (await db.execute(
            select(Candidate).where(
                Candidate.org_id == org_id,
                Candidate.job_posting_id == job.id,
            )
        )).scalars().all()
        counts: dict[str, int] = {k: 0 for k, _ in PIPELINE_STAGES}
        counts["rejected"] = 0
        for c in cands:
            counts[_stage_key(c.status)] = counts.get(_stage_key(c.status), 0) + 1
        # Conversion edges
        conv: dict[str, float] = {}
        for i in range(len(PIPELINE_STAGES) - 1):
            a_key = PIPELINE_STAGES[i][0]
            b_key = PIPELINE_STAGES[i + 1][0]
            a = counts.get(a_key, 0)
            b = counts.get(b_key, 0)
            if a + b == 0:
                conv[f"{a_key}->{b_key}"] = 0.0
            else:
                # Forward-flow conversion: people now at b OR beyond / people who entered a
                later = sum(counts.get(k, 0) for k, _ in PIPELINE_STAGES[i + 1:])
                entered = a + later
                conv[f"{a_key}->{b_key}"] = round((later / max(entered, 1)), 3)
        # Time-to-first-screen ≈ avg created→ai_screened transition. We don't
        # have per-stage timestamps, so approximate as candidates in ai_screened+.
        post_screen = [c for c in cands if STAGE_INDEX.get(_stage_key(c.status), -1) >= STAGE_INDEX["ai_screened"]]
        tts = round(statistics.mean([
            _days_between(c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at, now)
            for c in post_screen
        ]), 1) if post_screen else 0.0
        post_offer = [c for c in cands if STAGE_INDEX.get(_stage_key(c.status), -1) >= STAGE_INDEX["offer"]]
        tto = round(statistics.mean([
            _days_between(c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at, now)
            for c in post_offer
        ]), 1) if post_offer else 0.0
        open_days = int(_days_between(
            job.created_at.replace(tzinfo=timezone.utc) if job.created_at.tzinfo is None else job.created_at,
            now,
        ))
        out.append(FunnelMetrics(
            job_id=str(job.id),
            job_title=job.title,
            counts=counts,
            conversion=conv,
            time_to_first_screen_days=tts,
            time_to_offer_days=tto,
            open_days=open_days,
        ))
    return out


# ---------------------------------------------------------------------------
# 5. Candidate insights — adjacent skills, trajectory, mobility
# ---------------------------------------------------------------------------
_SENIORITY_PATTERN = re.compile(
    r"\b(intern|junior|associate|sr\.?|senior|staff|principal|distinguished|"
    r"lead|manager|sr\.?\s*manager|director|vp|svp|cto|cpo|chief|head\s+of)\b",
    re.IGNORECASE,
)
_TRAJECTORY_HINTS = [
    "intern", "junior", "associate", "engineer", "senior", "staff", "principal",
    "manager", "senior manager", "director", "vp", "head", "chief",
]


def _trajectory_from_text(text: str) -> tuple[list[str], str]:
    if not text:
        return [], "IC1-3"
    found: list[str] = []
    for h in _TRAJECTORY_HINTS:
        if re.search(rf"\b{re.escape(h)}\b", text, re.IGNORECASE):
            if h.title() not in found:
                found.append(h.title())
    # Seniority estimate based on highest hit
    senior_idx = -1
    seniority_label = "IC1-3"
    seniority_map = [
        (["intern"], "intern"),
        (["junior", "associate"], "IC1-3"),
        (["engineer", "developer"], "IC1-3"),
        (["senior"], "IC4"),
        (["staff", "principal", "distinguished"], "IC5+"),
        (["manager"], "manager"),
        (["senior manager", "sr manager"], "sr_manager"),
        (["director", "head"], "director"),
        (["vp", "chief", "cto", "cpo", "svp"], "executive"),
    ]
    for i, (keys, label) in enumerate(seniority_map):
        for k in keys:
            if re.search(rf"\b{re.escape(k)}\b", text, re.IGNORECASE) and i > senior_idx:
                senior_idx = i
                seniority_label = label
    return found, seniority_label


async def candidate_insights(
    db: AsyncSession,
    org_id: UUID,
    candidate_id: UUID,
) -> Optional[CandidateInsight]:
    c = (await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.org_id == org_id)
    )).scalar_one_or_none()
    if not c:
        return None

    job = None
    if c.job_posting_id:
        job = (await db.execute(
            select(JobPosting).where(JobPosting.id == c.job_posting_id)
        )).scalar_one_or_none()

    resume = c.resume_text or ""
    cand_skills, _ = extract_skills(resume)
    job_skills, _ = extract_skills(job.description if job else "")
    overlap = sorted(cand_skills & job_skills) if job else sorted(cand_skills)[:6]
    adjacent = sorted(cand_skills - job_skills)[:8] if job else []
    trajectory, seniority = _trajectory_from_text(resume)

    # Internal mobility: anyone with hire signal + strong adjacent skills
    # could move into another role.
    mobility = len(adjacent) >= 4 and (c.ai_score or 0) >= 60

    promotion_readiness = 0.0
    if cand_skills:
        promotion_readiness = min(1.0, (
            0.5 * (len(overlap) / max(len(job_skills), 1) if job_skills else 0.4)
            + 0.3 * (1.0 if seniority in ("IC4", "IC5+", "manager", "sr_manager") else 0.4)
            + 0.2 * (1.0 if c.ai_score and c.ai_score >= 70 else 0.3)
        ))

    summary = (
        f"{c.full_name} aligns on {len(overlap)} of {len(job_skills) or '?'} role skills"
        + (f" — strongest on {', '.join(overlap[:3])}" if overlap else "")
        + f". Trajectory: {' → '.join(trajectory[-4:]) if trajectory else 'unknown'}."
        + f" Seniority est. {seniority}."
    )

    return CandidateInsight(
        candidate_id=str(c.id),
        candidate_name=c.full_name,
        job_id=str(c.job_posting_id) if c.job_posting_id else None,
        job_title=job.title if job else None,
        headline_skills=overlap[:6],
        adjacent_skills=adjacent,
        career_trajectory=trajectory,
        seniority_estimate=seniority,
        internal_mobility_flag=mobility,
        promotion_readiness=round(promotion_readiness, 2),
        summary=summary,
    )


# ---------------------------------------------------------------------------
# 6. Talent pool auto-bucketing
# ---------------------------------------------------------------------------
_POOL_DEFINITIONS = [
    ("eng-python",     "Python backend",        {"python", "fastapi", "django", "flask", "asyncio", "postgres"}),
    ("eng-frontend",   "Frontend / React",      {"react", "typescript", "next.js", "tailwind", "redux"}),
    ("eng-ai-ml",      "AI / ML",               {"pytorch", "tensorflow", "ml", "llm", "embeddings", "vector", "rag", "transformers"}),
    ("eng-devops",     "Platform / DevOps",     {"kubernetes", "terraform", "aws", "docker", "ci/cd", "observability"}),
    ("design",         "Design / Product",      {"figma", "ux", "ui", "prototype", "research", "design"}),
    ("sales",          "Sales",                 {"sales", "quota", "pipeline", "close", "outbound", "ae", "saas"}),
    ("pm",             "Product",               {"product", "roadmap", "discovery", "prd", "stakeholder"}),
    ("marketing",      "Marketing",             {"growth", "seo", "content", "demand", "campaign", "brand"}),
    ("ops",            "Operations / Finance",  {"ops", "finance", "accounting", "compliance", "audit"}),
]


async def talent_pools(db: AsyncSession, org_id: UUID) -> list[TalentPool]:
    cands = (await db.execute(
        select(Candidate).where(Candidate.org_id == org_id)
    )).scalars().all()
    by_pool: dict[str, list[Candidate]] = {pid: [] for pid, _, _ in _POOL_DEFINITIONS}
    sigs: dict[str, list[str]] = {pid: [] for pid, _, _ in _POOL_DEFINITIONS}
    for c in cands:
        if not c.resume_text:
            continue
        cand_skills, _ = extract_skills(c.resume_text)
        for pid, _, sig in _POOL_DEFINITIONS:
            if cand_skills & sig:
                by_pool[pid].append(c)
                sigs[pid].extend(list(cand_skills & sig)[:3])
    out: list[TalentPool] = []
    for pid, name, _ in _POOL_DEFINITIONS:
        members = by_pool[pid]
        if not members:
            continue
        avg = round(sum((m.ai_score or 0) for m in members) / max(len(members), 1), 1)
        # dedupe + cap signature
        seen: set[str] = set()
        sig_list: list[str] = []
        for s in sigs[pid]:
            if s not in seen:
                seen.add(s)
                sig_list.append(s)
            if len(sig_list) >= 6:
                break
        out.append(TalentPool(
            id=pid,
            name=name,
            description=f"{len(members)} candidate{'s' if len(members) != 1 else ''} matching {name.lower()} signature.",
            candidate_ids=[str(m.id) for m in members],
            skill_signature=sig_list,
            avg_score=avg,
        ))
    out.sort(key=lambda p: -len(p.candidate_ids))
    return out


# ---------------------------------------------------------------------------
# 7. Recruiter productivity + candidate experience
# ---------------------------------------------------------------------------
async def recruiter_productivity(db: AsyncSession, org_id: UUID) -> RecruiterProductivity:
    jobs = (await db.execute(
        select(JobPosting).where(JobPosting.org_id == org_id, JobPosting.status != "archived")
    )).scalars().all()
    cands = (await db.execute(
        select(Candidate).where(Candidate.org_id == org_id)
    )).scalars().all()
    now = _now_utc()
    open_reqs = len(jobs)
    in_flight = [c for c in cands if _stage_key(c.status) not in TERMINAL_STAGES]
    added_7d = [c for c in cands if _days_between(
        c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at, now,
    ) <= 7]
    interviews_30d = [c for c in cands if _stage_key(c.status) in ("interview", "offer", "hired") and _days_between(
        c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at, now,
    ) <= 30]
    tts_post = [c for c in cands if STAGE_INDEX.get(_stage_key(c.status), -1) >= STAGE_INDEX["ai_screened"]]
    tts = round(statistics.mean([_days_between(
        c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at, now,
    ) for c in tts_post]), 1) if tts_post else 0.0
    tto_post = [c for c in cands if STAGE_INDEX.get(_stage_key(c.status), -1) >= STAGE_INDEX["offer"]]
    tto = round(statistics.mean([_days_between(
        c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at, now,
    ) for c in tto_post]), 1) if tto_post else 0.0
    bottlenecks = await detect_bottlenecks(db, org_id)
    critical = sum(1 for b in bottlenecks if b.severity == "critical")
    silent = [
        c for c in in_flight
        if _days_between(
            c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at,
            now,
        ) >= 3 and _stage_key(c.status) in ("applied", "ai_screened")
    ]
    notes: list[str] = []
    if critical:
        notes.append(f"{critical} requisition{'s' if critical != 1 else ''} have critical-stage stalls — top of the list to clear today.")
    if len(silent) >= 5:
        notes.append(f"{len(silent)} candidates have had no recruiter action in 3+ days. Risk: ghosting and candidate experience drop.")
    if tts > 4:
        notes.append(f"Time-to-first-screen is {tts}d — industry median is ~2d. Speed up the first touch to protect funnel.")
    if not notes:
        notes.append("Pipeline pacing looks healthy across all open requisitions.")
    return RecruiterProductivity(
        open_reqs=open_reqs,
        candidates_in_flight=len(in_flight),
        candidates_added_7d=len(added_7d),
        interviews_done_30d=len(interviews_30d),
        avg_time_to_first_screen_days=tts,
        avg_time_to_offer_days=tto,
        bottlenecks_critical=critical,
        silent_candidates_3d=len(silent),
        notes=notes,
    )


async def candidate_experience_signals(
    db: AsyncSession,
    org_id: UUID,
    *,
    limit: int = 12,
) -> list[CandidateExperienceSignal]:
    cands = (await db.execute(
        select(Candidate).where(Candidate.org_id == org_id)
    )).scalars().all()
    now = _now_utc()
    out: list[CandidateExperienceSignal] = []
    for c in cands:
        stage = _stage_key(c.status)
        if stage in TERMINAL_STAGES:
            continue
        days = int(_days_between(
            c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at,
            now,
        ))
        risk = "ok"
        note = ""
        if days >= 21 and stage in ("applied", "ai_screened"):
            risk = "ghosted"
            note = f"21+ days in {stage} without progression — almost certainly lost."
        elif days >= 10 and stage in ("applied", "ai_screened"):
            risk = "stalled"
            note = f"Sitting in {stage} for {days}d — high disengagement risk."
        elif days >= 5 and stage in ("applied", "ai_screened"):
            risk = "delay"
            note = f"{days}d in {stage} — overdue first response."
        if risk != "ok":
            out.append(CandidateExperienceSignal(
                candidate_id=str(c.id),
                candidate_name=c.full_name,
                stage=stage,
                days_in_stage=days,
                last_touch_days=days,
                risk=risk,
                note=note,
            ))
    risk_order = {"ghosted": 0, "stalled": 1, "delay": 2, "ok": 3}
    out.sort(key=lambda s: (risk_order.get(s.risk, 9), -s.days_in_stage))
    return out[:limit]


# ---------------------------------------------------------------------------
# 8. Scorecard rollup — combine AI screen + interview + reference signals
# ---------------------------------------------------------------------------
def rollup_scorecard(
    *,
    candidate_id: str,
    candidate_name: str,
    job_id: Optional[str],
    ai_screen_score: Optional[int],
    interview_overall: Optional[int],
    interview_dimensions: Optional[dict[str, int]] = None,
    reference_overall: Optional[int],
    reference_band: Optional[str],
    notes: Optional[list[str]] = None,
) -> ScorecardRollup:
    interview_dimensions = interview_dimensions or {}
    notes = notes or []

    # Composite — weighted blend, only count what's present
    components: list[tuple[float, int]] = []
    if ai_screen_score is not None:
        components.append((0.25, ai_screen_score))
    if interview_overall is not None:
        components.append((0.45, interview_overall))
    if reference_overall is not None:
        components.append((0.30, reference_overall))
    if not components:
        composite = 0
    else:
        total_w = sum(w for w, _ in components)
        composite = int(round(sum(w * s for w, s in components) / total_w))

    # Recommendation chain
    if composite >= 78:
        rec = "advance"
    elif composite >= 60:
        rec = "advance"
    elif composite >= 45:
        rec = "advance_with_caveats"
    elif composite >= 30:
        rec = "hold"
    else:
        rec = "decline"

    # Reference band can downgrade
    if reference_band in ("do_not_endorse",):
        rec = "decline"
    elif reference_band == "lukewarm" and rec in ("advance",):
        rec = "advance_with_caveats"

    strengths: list[str] = []
    risks: list[str] = []
    if interview_overall is not None and interview_overall >= 70:
        strengths.append(f"Strong AI interview ({interview_overall}/100).")
    if reference_overall is not None and reference_overall >= 70:
        strengths.append(f"Strong reference signal ({reference_overall}/100).")
    if interview_dimensions.get("expression", 0) >= 80:
        strengths.append("Confident, on-camera communication.")
    if interview_dimensions.get("technical", 0) < 40:
        risks.append("Technical depth below bar — probe in next round.")
    if reference_band == "lukewarm":
        risks.append("Reference is lukewarm — surface the specific reservation.")
    if reference_band == "do_not_endorse":
        risks.append("Reference declined to endorse — recommend declining.")

    next_actions: list[str] = []
    if rec == "advance":
        next_actions.append("Schedule onsite / final round.")
    elif rec == "advance_with_caveats":
        next_actions.append("Add one targeted interviewer on the weak area.")
    elif rec == "hold":
        next_actions.append("Park in talent pool; revisit when bar drops or signal strengthens.")
    elif rec == "decline":
        next_actions.append("Send polite decline; add to nurture pool if culture fit was strong.")

    return ScorecardRollup(
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        job_id=job_id,
        ai_screen_score=ai_screen_score,
        interview_overall=interview_overall,
        interview_dimensions=interview_dimensions,
        reference_overall=reference_overall,
        reference_band=reference_band,
        composite_score=composite,
        recommendation=rec,
        strengths=strengths,
        risks=risks,
        next_actions=next_actions,
    )
