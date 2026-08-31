"""Universal activity timeline.

Surfaces what happened across the org in one calm, linear feed. Reads from
the existing audit_events table, then layers in agent runs, recent task
updates, and HR moments (new hires, cycles started).

Filterable by category. Designed to be the "audit timeline architecture"
the brief called out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_runtime import list_runs
from app.services.tasks_service import list_tasks


@dataclass
class ActivityEvent:
    id: str
    kind: str               # workflow | agent | task | people | compliance | comp | hire | system
    title: str
    detail: str = ""
    actor: Optional[str] = None
    actor_role: Optional[str] = None
    subject: Optional[str] = None
    cta_href: Optional[str] = None
    severity: str = "neutral"     # neutral | info | warn | success | danger
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return self.__dict__


KIND_OF_EVENT = {
    "case.created": "compliance",
    "case.assigned": "compliance",
    "case.findings_recorded": "compliance",
    "case.action_taken": "compliance",
    "case.closed": "compliance",
    "candidate.screened": "hire",
    "candidate.stage_changed": "hire",
    "candidate.decision": "hire",
    "job.created": "hire",
    "onboarding.packet.created": "workflow",
    "agent.installed": "system",
    "agent.uninstalled": "system",
    "memory.bulk_ingest": "system",
    "exec_copilot.ask": "system",
    "ombudsman.ai_summary": "compliance",
    "resume_ai.match": "hire",
    "resume_ai.screen_job": "hire",
    "ai_interview.created": "hire",
    "ai_interview.completed": "hire",
    "comp_ai.recommend": "comp",
    "comp_ai.recommend_batch": "comp",
    "ai_helpdesk.ask": "system",
    "ai_helpdesk.document_added": "system",
}


def _humanize_event(et: str) -> tuple[str, str]:
    """Return (title, severity) for an audit event type."""
    if "decision" in et:
        return ("Hiring decision recorded", "success")
    if "candidate" in et and "stage" in et:
        return ("Candidate moved stage", "info")
    if "job.created" in et:
        return ("New job posting", "success")
    if "case.created" in et:
        return ("New ombudsman case", "warn")
    if "case.closed" in et:
        return ("Ombudsman case closed", "success")
    if "comp_ai" in et:
        return ("Compensation recommendation generated", "info")
    if "ai_interview.completed" in et:
        return ("AI interview completed", "info")
    if "ai_interview.created" in et:
        return ("AI interview launched", "info")
    if "memory" in et:
        return ("Knowledge document ingested", "neutral")
    if "agent.installed" in et:
        return ("Agent installed", "success")
    if "agent.uninstalled" in et:
        return ("Agent uninstalled", "neutral")
    if "ombudsman.ai_summary" in et:
        return ("Case AI summary generated", "info")
    if "exec_copilot" in et:
        return ("Executive copilot asked", "neutral")
    if "ai_helpdesk" in et:
        return ("Helpdesk question asked", "neutral")
    return (et.replace(".", " · "), "neutral")


async def _audit_events(db: AsyncSession, org_id: str, limit: int = 80) -> list[ActivityEvent]:
    try:
        res = await db.execute(
            text(
                """
                select id::text as id, event_type, actor_role, payload, created_at, entity_type, entity_id::text as entity_id
                from public.audit_events
                where org_id=:org
                order by created_at desc
                limit :limit
                """
            ),
            {"org": org_id, "limit": limit},
        )
        rows = [dict(r) for r in res.mappings().all()]
    except Exception:
        rows = []
    out: list[ActivityEvent] = []
    for r in rows:
        kind = KIND_OF_EVENT.get(r["event_type"], "workflow")
        title, severity = _humanize_event(r["event_type"])
        payload = r.get("payload") or {}
        detail_parts: list[str] = []
        if isinstance(payload, dict):
            for k in ("score", "recommendation", "decision", "job_id", "case_id", "candidate_id"):
                if k in payload:
                    detail_parts.append(f"{k}: {payload[k]}")
        cta_href: Optional[str] = None
        ent = (r.get("entity_type") or "").lower()
        if "case" in ent:
            cta_href = "/app/ombudsman"
        elif "candidate" in ent:
            cta_href = "/app/talent"
        elif "job" in ent:
            cta_href = "/app/recruiting"
        elif "agent" in ent:
            cta_href = "/app/agents"
        out.append(ActivityEvent(
            id=f"audit-{r['id']}",
            kind=kind,
            title=title,
            detail=" · ".join(detail_parts),
            actor_role=r.get("actor_role"),
            subject=(r.get("entity_type") or "") + " " + (r.get("entity_id") or "")[:8],
            severity=severity,
            cta_href=cta_href,
            created_at=str(r["created_at"]),
        ))
    return out


def _agent_run_events(org_id: str) -> list[ActivityEvent]:
    out: list[ActivityEvent] = []
    for r in list_runs(org_id):
        out.append(ActivityEvent(
            id=f"agent-run-{r.id}",
            kind="agent",
            title=f"{r.agent.replace('_', ' ').title()} agent run",
            detail=r.summary,
            severity="info" if r.confidence in ("high", "medium") else "neutral",
            cta_href=f"/app/agents?agent={r.agent}",
            created_at=r.started_at,
        ))
    return out


def _task_events(org_id: str) -> list[ActivityEvent]:
    out: list[ActivityEvent] = []
    tasks = list_tasks(org_id)
    for t in tasks[:25]:
        sev = "warn" if t["status"] == "blocked" else "success" if t["status"] == "done" else "neutral"
        out.append(ActivityEvent(
            id=f"task-{t['id']}",
            kind="task",
            title=t["title"],
            detail=f"{t.get('source','')} · {t['status']}",
            subject=t.get("related_employee_name") or t.get("project"),
            actor=t.get("owner_name"),
            actor_role=t.get("owner_role"),
            severity=sev,
            cta_href="/app/work",
            created_at=t.get("updated_at") or t.get("created_at"),
        ))
    return out


async def feed(db: AsyncSession, org_id: str, *, kind: Optional[str] = None, limit: int = 60) -> dict:
    events: list[ActivityEvent] = []
    events.extend(await _audit_events(db, org_id, limit=120))
    events.extend(_agent_run_events(org_id))
    events.extend(_task_events(org_id))

    # Sort by created_at desc, treat missing as "now"
    def _key(e: ActivityEvent) -> str:
        return e.created_at or ""

    events.sort(key=_key, reverse=True)
    if kind:
        events = [e for e in events if e.kind == kind]
    events = events[:limit]

    counts: dict[str, int] = {}
    for e in events:
        counts[e.kind] = counts.get(e.kind, 0) + 1

    return {
        "items": [e.to_dict() for e in events],
        "counts": counts,
        "kinds": ["workflow", "agent", "task", "people", "compliance", "comp", "hire", "system"],
    }
