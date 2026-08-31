"""Content generation utilities — JDs, interview scorecards, balanced-feedback
rewriter, onboarding checklists.

All functions return structured dicts so the UI can render rich sections (not
just a paragraph). LLM is used when available; deterministic templates fall
back so the demo always produces useful output.
"""
from __future__ import annotations

import re
import textwrap
from typing import Optional

from app.services.learning_service import required_skills_for

try:
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


# ---------------------------------------------------------------------------
def _llm(prompt: str, system: str) -> Optional[str]:
    if llm_complete is None:
        return None
    try:
        return llm_complete(prompt, system=system)
    except (LLMError, Exception):
        return None


# ---------------------------------------------------------------------------
# JOB DESCRIPTION
# ---------------------------------------------------------------------------
def generate_job_description(title: str, level: str = "mid", department: str = "",
                              location: str = "Remote", notes: str = "") -> dict:
    skills = required_skills_for(title) or required_skills_for(f"{level} {title}") or []

    sections = {
        "title": title,
        "level": level,
        "department": department or "—",
        "location": location,
        "summary": f"We're hiring a {level} {title} to join {department or 'the team'}. "
                   f"You will own meaningful scope, ship to real customers, and grow alongside the org.",
        "responsibilities": [
            f"Own end-to-end delivery of {title}-scoped work.",
            "Collaborate with cross-functional partners across product, design, and go-to-market.",
            "Raise the bar on quality, reliability, and team practices.",
            "Mentor peers and contribute to a calm, focused culture.",
        ],
        "required_skills": skills or ["communication", "leadership"],
        "nice_to_have": ["startup experience", "remote-first comfort"],
        "compensation_note": "Compensation is benchmarked to market and adjusted for role + location.",
        "inclusion_statement": (
            "Foundry People is an equal-opportunity employer. We assess every "
            "applicant on the merits of their experience and potential. We make "
            "accommodations on request for the interview process."
        ),
        "notes": notes,
    }

    enriched = _llm(
        textwrap.dedent(f"""
            Rewrite this draft JD with calm, inclusive, specific language. Keep the
            same JSON keys. Output JSON only.
            {sections}
        """).strip(),
        system="You write job descriptions that are short, specific, and bias-free.",
    )
    if enriched:
        sections["llm_enriched"] = enriched

    return sections


# ---------------------------------------------------------------------------
# INTERVIEW SCORECARD
# ---------------------------------------------------------------------------
def generate_interview_scorecard(role: str, competencies: Optional[list[str]] = None) -> dict:
    competencies = competencies or ["role_fit", "technical_depth", "problem_solving",
                                    "communication", "ownership", "collaboration", "values_alignment"]
    return {
        "role": role,
        "rubric": [
            {
                "competency": c,
                "levels": [
                    {"score": 1, "name": "below_bar", "description": "Significant gaps for the level."},
                    {"score": 2, "name": "developing", "description": "Foundations present but inconsistent."},
                    {"score": 3, "name": "meets",      "description": "Clear, repeatable evidence at the level."},
                    {"score": 4, "name": "exceeds",    "description": "Notably above the bar; pulls up the team."},
                    {"score": 5, "name": "stretch",    "description": "Promotion-ready; defines a new level."},
                ],
                "evidence_prompts": [
                    f"Give a specific example from the last 12 months that shows {c.replace('_', ' ')}.",
                    "What was the situation, your role, and the measurable outcome?",
                    "What would you do differently with hindsight?",
                ],
            }
            for c in competencies
        ],
        "fairness_note": (
            "Use this scorecard for every candidate in this role. Avoid notes about "
            "appearance, accent, age, gender, family status, or other protected attributes. "
            "Calibrate scores against the rubric before debrief."
        ),
    }


# ---------------------------------------------------------------------------
# FEEDBACK REWRITER (bias + vagueness detection)
# ---------------------------------------------------------------------------
_VAGUE_PATTERNS = [
    r"\bnice\b", r"\bnice to have\b", r"\bgreat\b", r"\bawesome\b",
    r"\bteam player\b", r"\bgood guy\b", r"\bgood girl\b",
    r"\bbrings energy\b", r"\bsoft\b", r"\baggressive\b",
    r"\babrasive\b", r"\bbossy\b", r"\bemotional\b",
]


def detect_vague_or_biased(text: str) -> dict:
    txt = (text or "").strip()
    flags: list[dict] = []
    for pat in _VAGUE_PATTERNS:
        m = re.search(pat, txt, flags=re.IGNORECASE)
        if m:
            flags.append({
                "term": m.group(0),
                "kind": "bias_risk" if pat in (r"\bbossy\b", r"\baggressive\b", r"\babrasive\b", r"\bemotional\b") else "vague",
                "suggestion": "Replace with a specific behaviour + measurable outcome.",
            })
    # Generic catch — too short
    word_count = len(txt.split())
    if word_count < 25:
        flags.append({"kind": "too_short", "suggestion": "Add a concrete example or measurable outcome."})
    return {"flags": flags, "word_count": word_count}


def rewrite_balanced(text: str, employee_name: str = "the employee") -> dict:
    detection = detect_vague_or_biased(text)
    composed = _llm(
        textwrap.dedent(f"""
            Rewrite this manager feedback to be specific, bias-free, and balanced
            (strengths + growth + measurable outcome). Use "{employee_name}" as the
            subject. Keep it under 120 words. Plain prose, no headers.

            Original:
            {text}
        """).strip(),
        system="You are a calibrated HR coach. Replace vague or biased language with specific behaviours and outcomes.",
    )
    fallback = (
        f"{employee_name} consistently delivered against the team's commitments this period. "
        "Specific example: led the ABC initiative, shipped on date, and saw a +15% measured impact on the target metric. "
        "Area to grow: scope wider influence — bring more peers into design reviews earlier so decisions are co-owned. "
        "Recommended next step: pair on one cross-team project before the next review cycle."
    )
    return {
        "original": text,
        "detected": detection,
        "rewrite": composed or fallback,
        "disclaimer": "AI-rewritten draft. Manager must review and confirm before sharing.",
    }


# ---------------------------------------------------------------------------
# ONBOARDING PLAN GENERATOR
# ---------------------------------------------------------------------------
def generate_onboarding_plan(employee_name: str, role: str, manager_name: str = "your manager",
                              start_date: str = "Day 1") -> dict:
    skills = required_skills_for(role) or []
    return {
        "employee": employee_name,
        "role": role,
        "manager": manager_name,
        "start_date": start_date,
        "pre_day_1": [
            "Sign offer in Dropbox Sign",
            "Complete I-9 and direct deposit setup",
            "Pick up equipment (delivered to your address)",
            "Receive welcome message and Day-1 schedule",
        ],
        "first_week": [
            "Manager 1:1 — context, expectations, calendar",
            "Buddy intro + tour of internal docs",
            "Security & compliance training (required)",
            "Shadow 2 customer or operations meetings",
        ],
        "first_30_days": [
            "Complete role-specific learning path",
            "Ship one small but visible piece of work",
            "Map your stakeholders and align on success metrics",
        ],
        "first_60_days": [
            "Take ownership of a recurring meeting or workstream",
            "Deliver a written summary of what you've learned",
            "Calibrate goals with manager for the next quarter",
        ],
        "first_90_days": [
            "Independently drive a project end-to-end",
            "Mentor or onboard the next teammate",
            "First formal performance check-in",
        ],
        "skill_focus": skills,
        "checklist_owner_roles": ["new_hire", "manager", "hr", "it"],
    }
