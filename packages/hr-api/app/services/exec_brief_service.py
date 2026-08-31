"""Executive morning brief.

A narrative-first daily briefing for SMB owners / execs that combines:
- workforce headlines (CPO synthesis)
- risk score + top alerts
- hiring funnel health
- payroll / comp trends (heuristic until /payroll lands)
- learning + compliance posture
- AI-generated 3-line narrative + headline

This is intentionally distinct from the command center: it's a *story* you read
once per morning, not a workbench.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cpo_service import build_report
from app.services.workforce_risk_service import scan as scan_risk
from app.services.tasks_service import tasks_summary

try:
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


@dataclass
class BriefBlock:
    title: str
    summary: str
    detail: str = ""
    tone: str = "neutral"   # neutral | success | warn | danger | info
    cta_label: Optional[str] = None
    cta_href: Optional[str] = None

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ExecutiveBrief:
    generated_at: str
    headline: str
    narrative: str
    counts: dict
    blocks: list[BriefBlock] = field(default_factory=list)
    suggested_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "headline": self.headline,
            "narrative": self.narrative,
            "counts": self.counts,
            "blocks": [b.to_dict() for b in self.blocks],
            "suggested_questions": self.suggested_questions,
        }


async def _scalar(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        row = (await db.execute(text(sql), params)).first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _llm_narrative(facts: dict) -> Optional[str]:
    if llm_complete is None:
        return None
    try:
        prompt = textwrap.dedent(f"""
            You are the executive copilot for an SMB CEO. Write a 3-sentence
            morning briefing using ONLY the facts below. Calm, confident, no
            numbers invented. Reference at most 2 numbers.

            Facts:
            {facts}
        """).strip()
        return llm_complete(prompt, system="Tone: calm, specific, never invent metrics.")
    except (LLMError, Exception):
        return None


def _fallback_narrative(headline: str, cpo_summary: str, risk_score: int, risk_headline: str) -> str:
    parts = [headline, cpo_summary or "", f"Workforce risk score is {risk_score}/100.", risk_headline or ""]
    return " ".join([p for p in parts if p])


async def build_brief(db: AsyncSession, org_id: str) -> ExecutiveBrief:
    cpo = await build_report(db, org_id)
    risk = await scan_risk(db, org_id)
    tasks = tasks_summary(org_id)

    employees_total = await _scalar(
        db, "select count(*) from public.employees where org_id=:org_id", {"org_id": org_id},
    )
    employees_invited = await _scalar(
        db, "select count(*) from public.employees where org_id=:org_id and status='invited'", {"org_id": org_id},
    )
    open_jobs = await _scalar(
        db, "select count(*) from public.job_postings where org_id=:org_id and status<>'closed'", {"org_id": org_id},
    )
    candidates_total = await _scalar(
        db, "select count(*) from public.candidates where org_id=:org_id", {"org_id": org_id},
    )
    candidates_offer = await _scalar(
        db, "select count(*) from public.candidates where org_id=:org_id and status='offer'", {"org_id": org_id},
    )
    cases_high_open = await _scalar(
        db, "select count(*) from public.cases where org_id=:org_id and severity='high' and status<>'closed'", {"org_id": org_id},
    )

    counts = {
        "headcount": employees_total,
        "open_jobs": open_jobs,
        "candidates_total": candidates_total,
        "candidates_offer": candidates_offer,
        "cases_high_open": cases_high_open,
        "workforce_risk_score": risk.score,
        "tasks_open": tasks["open"],
        "tasks_overdue": tasks["overdue"],
        "new_hires_pending": employees_invited,
    }

    # Blocks
    blocks: list[BriefBlock] = []

    blocks.append(BriefBlock(
        title="Workforce",
        tone="info",
        # "1 employees · 0 new hires" reads as a placeholder, and an exec brief
        # is the one screen where every word is read.
        summary=(f"{employees_total} employee{'s' if employees_total != 1 else ''} · "
                 f"{employees_invited} new hire{'s' if employees_invited != 1 else ''} "
                 "pending Day 1"),
        detail=cpo.summary,
        cta_label="People overview",
        cta_href="/app/people",
    ))

    pipeline_health = "healthy" if open_jobs and candidates_total >= open_jobs * 5 else "thin" if open_jobs else "no open roles"
    blocks.append(BriefBlock(
        title="Hiring",
        tone="warn" if pipeline_health == "thin" else "neutral",
        summary=(f"{open_jobs} open role{'s' if open_jobs != 1 else ''} · "
                 f"{candidates_total} candidate{'s' if candidates_total != 1 else ''} · "
                 f"pipeline {pipeline_health}"),
        detail=(f"{candidates_offer} candidate{'s' if candidates_offer != 1 else ''} "
                "currently at offer." if candidates_offer
                else "No offers in motion right now."),
        cta_label="Talent",
        cta_href="/app/talent",
    ))

    blocks.append(BriefBlock(
        title="Risk",
        tone="danger" if risk.score >= 65 else "warn" if risk.score >= 40 else "success",
        summary=f"Workforce risk score {risk.score}/100",
        detail=risk.headline,
        cta_label="Risk engine",
        cta_href="/app/risk",
    ))

    blocks.append(BriefBlock(
        title="Compliance",
        tone="danger" if cases_high_open else "success",
        summary=f"{cases_high_open} high-severity case{'s' if cases_high_open != 1 else ''} open",
        detail="Investigations need triage. Route to HR + legal." if cases_high_open else "No high-severity cases open.",
        cta_label="Ombudsman",
        cta_href="/app/ombudsman",
    ))

    blocks.append(BriefBlock(
        title="Execution",
        tone="warn" if tasks["overdue"] else "neutral",
        summary=(f"{tasks['open']} open task{'s' if tasks['open'] != 1 else ''} · "
                 f"{tasks['overdue']} overdue"),
        detail=(f"{tasks['ai_generated_open']} "
                f"{'was' if tasks['ai_generated_open'] == 1 else 'were'} "
                "auto-orchestrated by the HR agents."),
        cta_label="Work hub",
        cta_href="/app/work",
    ))

    # Narrative
    facts = {
        "headline": cpo.headline,
        "summary": cpo.summary,
        "risk_score": risk.score,
        "risk_headline": risk.headline,
        "open_jobs": open_jobs,
        "candidates": candidates_total,
        "candidates_offer": candidates_offer,
        "high_cases": cases_high_open,
        "tasks_overdue": tasks["overdue"],
    }
    narrative = _llm_narrative(facts) or _fallback_narrative(cpo.headline, cpo.summary, risk.score, risk.headline)

    suggested = [
        "How healthy is the company this week?",
        "Where are we most exposed on hiring?",
        "Which employees are at the highest attrition risk?",
        "Any compensation issues I should know about?",
    ]

    return ExecutiveBrief(
        generated_at=datetime.now(timezone.utc).isoformat(),
        headline=cpo.headline,
        narrative=narrative,
        counts=counts,
        blocks=blocks,
        suggested_questions=suggested,
    )
