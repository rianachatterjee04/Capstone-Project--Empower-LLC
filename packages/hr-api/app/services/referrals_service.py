"""Referral Intelligence — employee networks → open requisitions.

The Eightfold / Phenom / Beamery "talent intelligence" hero feature, reframed
for SMB: every employee carries an implicit network and a skill signature.
The service ranks open reqs against each employee's network so they see
exactly which role they're best positioned to refer for — and tracks the
referral all the way to hire + reward payout.

In-process demo store (consistent with ai_interview / reference_check) so
the demo runs without a migration. Production swap-in is a single ORM
model behind these dataclasses.
"""
from __future__ import annotations

import math
import re
import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ReferrerProfile:
    """Each employee has one — their declared network + expertise signal."""
    employee_id: str
    employee_name: str
    title: str = ""
    team: str = ""
    skills: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)  # e.g. "ex-Stripe", "Berkeley CS '18"
    referrals_made: int = 0
    referrals_hired: int = 0
    pending_reward_usd: float = 0.0
    lifetime_reward_usd: float = 0.0


@dataclass
class ReferralMatch:
    """A specific (referrer, requisition) match the system surfaces."""
    employee_id: str
    employee_name: str
    job_id: str
    job_title: str
    match_score: int                # 0-100
    skill_overlap: list[str]
    network_overlap: list[str]
    rationale: str
    reward_usd: float


@dataclass
class Referral:
    id: str
    org_id: str
    referrer_employee_id: str
    referrer_name: str
    job_id: str
    job_title: str
    candidate_name: str
    candidate_email: str = ""
    relationship: str = "former_colleague"   # former_colleague / friend / community / family
    note: str = ""
    status: str = "submitted"      # submitted / contacted / interviewing / hired / not_hired / withdrawn
    reward_usd: float = 0.0
    reward_status: str = "pending"  # pending / earned / paid
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# In-process stores
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_referrals: dict[str, dict[str, Referral]] = {}  # org_id -> referral_id -> Referral
_referrer_profiles: dict[str, dict[str, ReferrerProfile]] = {}  # org_id -> employee_id -> profile


# ---------------------------------------------------------------------------
# Demo seed — only fires when an org first reads the data
# ---------------------------------------------------------------------------
_DEMO_PROFILES = [
    ("emp-1", "Sarah Chen",   "VP Engineering",  "Atlas",
     ["python", "fastapi", "postgres", "kubernetes", "leadership"],
     ["ex-Stripe", "ex-Coinbase", "Berkeley CS"]),
    ("emp-2", "Atiman Rao",   "Sr Backend Eng",   "Atlas",
     ["python", "fastapi", "postgres", "asyncio", "llm"],
     ["IIT Bombay", "ex-Razorpay"]),
    ("emp-3", "Priya N",      "Eng Manager",     "Helios",
     ["typescript", "react", "node", "mentorship", "hiring"],
     ["ex-Linear", "Stanford CS"]),
    ("emp-4", "Marcus Patel", "Sr Product Mgr",   "Aurora",
     ["product", "discovery", "ux", "roadmap", "saas"],
     ["ex-Notion", "ex-Figma"]),
    ("emp-5", "Mia O.",        "Staff Designer",  "Nova",
     ["figma", "ux", "ui", "research", "prototype"],
     ["ex-Airbnb", "RISD"]),
    ("emp-6", "Jordan P.",    "Sr GTM",          "Vega",
     ["sales", "saas", "outbound", "pipeline", "closing"],
     ["ex-Salesforce", "ex-Datadog"]),
    ("emp-7", "Dana C.",      "Staff Eng",       "Atlas",
     ["distributed-systems", "go", "kubernetes", "observability"],
     ["ex-Google", "MIT EECS"]),
    ("emp-8", "Robin T.",     "Data Lead",       "Aurora",
     ["sql", "python", "dbt", "snowflake", "analytics"],
     ["ex-Databricks", "ex-Stripe"]),
]

_DEMO_JOBS = [
    ("job-1", "Senior Python Engineer",  ["python", "fastapi", "postgres", "asyncio"], 5000),
    ("job-2", "Founding ML Engineer",   ["python", "llm", "embeddings", "pytorch"], 7500),
    ("job-3", "Senior Frontend Engineer", ["typescript", "react", "node"], 4000),
    ("job-4", "Sr Product Manager",      ["product", "roadmap", "saas", "discovery"], 5000),
    ("job-5", "Staff Designer",           ["figma", "ux", "ui", "research"], 5000),
    ("job-6", "Enterprise AE",           ["sales", "saas", "outbound"], 6000),
]


def _ensure_demo_seed(org_id: str) -> None:
    with _lock:
        if org_id not in _referrer_profiles:
            _referrer_profiles[org_id] = {}
            for eid, name, title, team, skills, networks in _DEMO_PROFILES:
                _referrer_profiles[org_id][eid] = ReferrerProfile(
                    employee_id=eid, employee_name=name, title=title, team=team,
                    skills=skills, networks=networks,
                )
        if org_id not in _referrals:
            _referrals[org_id] = {}


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------
def _score_match(profile: ReferrerProfile, job_skills: list[str], job_title: str) -> tuple[int, list[str], list[str], str]:
    job_set = {s.lower() for s in job_skills}
    prof_set = {s.lower() for s in profile.skills}
    skill_overlap = sorted(job_set & prof_set)

    # Network heuristic: phrases like "ex-Stripe" / "ex-Coinbase" generally
    # correlate with stronger referral networks in tech. Treat each as a
    # weak positive signal.
    network_overlap: list[str] = []
    for net in profile.networks:
        if net.lower().startswith("ex-"):
            network_overlap.append(net)
        elif any(school in net.lower() for school in ["stanford", "mit", "berkeley", "cmu", "iit"]):
            network_overlap.append(net)

    skill_score = len(skill_overlap) / max(len(job_set), 1)
    network_score = min(1.0, len(network_overlap) / 3.0)
    # Title affinity — a Sr Engineer is a better referrer for Sr Engineer roles
    title_affinity = 0.0
    job_title_lower = job_title.lower()
    if profile.title:
        prof_title_words = set(profile.title.lower().split())
        job_title_words = set(job_title_lower.split())
        if prof_title_words & job_title_words:
            title_affinity = 0.5

    score = int(round(100 * (0.5 * skill_score + 0.3 * network_score + 0.2 * title_affinity)))
    rationale = (
        f"{len(skill_overlap)} skill match" + (f" ({', '.join(skill_overlap[:3])})" if skill_overlap else "")
        + (f" · {len(network_overlap)} network alignment" if network_overlap else "")
        + (f" · title affinity" if title_affinity > 0 else "")
    )
    return score, skill_overlap, network_overlap, rationale


def rank_employees_for_job(
    org_id: str,
    job_id: str,
    job_title: str,
    job_skills: list[str],
    *,
    limit: int = 8,
    min_score: int = 25,
) -> list[ReferralMatch]:
    _ensure_demo_seed(org_id)
    matches: list[ReferralMatch] = []
    reward = next((r for jid, _, _, r in _DEMO_JOBS if jid == job_id), 5000)
    for emp_id, prof in _referrer_profiles.get(org_id, {}).items():
        score, skill_overlap, network_overlap, rationale = _score_match(prof, job_skills, job_title)
        if score < min_score:
            continue
        matches.append(ReferralMatch(
            employee_id=emp_id,
            employee_name=prof.employee_name,
            job_id=job_id,
            job_title=job_title,
            match_score=score,
            skill_overlap=skill_overlap,
            network_overlap=network_overlap,
            rationale=rationale,
            reward_usd=float(reward),
        ))
    matches.sort(key=lambda m: -m.match_score)
    return matches[:limit]


def jobs_for_employee(org_id: str, employee_id: str, *, limit: int = 6) -> list[ReferralMatch]:
    """The employee-facing view — 'here are the open reqs where YOU are the
    best referrer in the company'."""
    _ensure_demo_seed(org_id)
    prof = _referrer_profiles.get(org_id, {}).get(employee_id)
    if not prof:
        return []
    out: list[ReferralMatch] = []
    for job_id, job_title, job_skills, reward in _DEMO_JOBS:
        score, skill_overlap, network_overlap, rationale = _score_match(prof, job_skills, job_title)
        if score < 25:
            continue
        out.append(ReferralMatch(
            employee_id=employee_id,
            employee_name=prof.employee_name,
            job_id=job_id,
            job_title=job_title,
            match_score=score,
            skill_overlap=skill_overlap,
            network_overlap=network_overlap,
            rationale=rationale,
            reward_usd=float(reward),
        ))
    out.sort(key=lambda m: -m.match_score)
    return out[:limit]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def submit_referral(
    org_id: str,
    referrer_employee_id: str,
    job_id: str,
    candidate_name: str,
    *,
    candidate_email: str = "",
    relationship: str = "former_colleague",
    note: str = "",
) -> Referral:
    _ensure_demo_seed(org_id)
    prof = _referrer_profiles.get(org_id, {}).get(referrer_employee_id)
    referrer_name = prof.employee_name if prof else "Unknown"
    job = next(((jt, rw) for jid, jt, _, rw in _DEMO_JOBS if jid == job_id), ("Unknown role", 5000))
    job_title, reward = job
    ref = Referral(
        id=str(uuid.uuid4()),
        org_id=org_id,
        referrer_employee_id=referrer_employee_id,
        referrer_name=referrer_name,
        job_id=job_id,
        job_title=job_title,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        relationship=relationship,
        note=note,
        reward_usd=float(reward),
    )
    with _lock:
        _referrals.setdefault(org_id, {})[ref.id] = ref
        if prof:
            prof.referrals_made += 1
            prof.pending_reward_usd += float(reward)
    return ref


def list_referrals(org_id: str) -> list[Referral]:
    _ensure_demo_seed(org_id)
    with _lock:
        items = list(_referrals.get(org_id, {}).values())
    items.sort(key=lambda r: r.created_at, reverse=True)
    return items


def update_referral_status(org_id: str, referral_id: str, status: str) -> Optional[Referral]:
    _ensure_demo_seed(org_id)
    with _lock:
        ref = _referrals.get(org_id, {}).get(referral_id)
        if not ref:
            return None
        ref.status = status
        ref.updated_at = datetime.now(timezone.utc).isoformat()
        prof = _referrer_profiles.get(org_id, {}).get(ref.referrer_employee_id)
        if status == "hired":
            ref.reward_status = "earned"
            if prof:
                prof.referrals_hired += 1
                prof.pending_reward_usd = max(0.0, prof.pending_reward_usd - ref.reward_usd)
                prof.lifetime_reward_usd += ref.reward_usd
        elif status in ("not_hired", "withdrawn"):
            ref.reward_status = "pending"
            if prof:
                prof.pending_reward_usd = max(0.0, prof.pending_reward_usd - ref.reward_usd)
        return ref


def leaderboard(org_id: str, *, limit: int = 10) -> list[ReferrerProfile]:
    _ensure_demo_seed(org_id)
    with _lock:
        items = list(_referrer_profiles.get(org_id, {}).values())
    items.sort(key=lambda p: (-p.referrals_hired, -p.referrals_made))
    return items[:limit]


def stats(org_id: str) -> dict:
    _ensure_demo_seed(org_id)
    refs = list_referrals(org_id)
    total = len(refs)
    hired = sum(1 for r in refs if r.status == "hired")
    in_progress = sum(1 for r in refs if r.status in ("submitted", "contacted", "interviewing"))
    rewards_paid = sum(r.reward_usd for r in refs if r.reward_status == "earned")
    rewards_pending = sum(r.reward_usd for r in refs if r.reward_status == "pending" and r.status != "withdrawn")
    return {
        "total_referrals": total,
        "hired": hired,
        "in_progress": in_progress,
        "hire_rate": round(hired / max(total, 1), 3),
        "rewards_earned_usd": round(rewards_paid, 2),
        "rewards_pending_usd": round(rewards_pending, 2),
        "active_referrers": len(_referrer_profiles.get(org_id, {})),
    }
