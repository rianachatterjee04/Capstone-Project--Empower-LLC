"""First-run setup wizard — Vanta-style guided checklist.

Each step has: id, title, description, owner role, optional CTA href, an
"is_done" predicate, and dependency hints. The state is derived live from
the rest of Foundry (employees, integrations, automations, agents) so the
checklist is always honest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import get_settings
from app.services.memory_service import memory_summary
from app.services.agent_marketplace_service import list_catalog


@dataclass
class WizardStep:
    id: str
    title: str
    description: str
    owner: str            # who typically owns this step
    cta_label: Optional[str] = None
    cta_href: Optional[str] = None
    done: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


async def _scalar(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        row = (await db.execute(text(sql), params)).first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


async def build_checklist(db: AsyncSession, org_id: str) -> dict:
    settings = get_settings(org_id)
    mem = memory_summary(org_id)
    catalog = list_catalog(org_id)
    installed_agents = sum(1 for a in catalog if a["installed"])

    employees_total = await _scalar(db, "select count(*) from public.employees where org_id=:org", {"org": org_id})
    jobs_total = await _scalar(db, "select count(*) from public.job_postings where org_id=:org", {"org": org_id})
    packets_total = await _scalar(db, "select count(*) from public.onboarding_packets where org_id=:org", {"org": org_id})

    payroll_connected = any(i["key"] in ("adp", "gusto") and i["connected"] for i in settings["integrations"])
    benefits_connected = any(i["key"] in ("guideline", "human_interest") and i["connected"] for i in settings["integrations"])
    messaging_connected = any(i["key"] in ("slack", "email") and i["connected"] for i in settings["integrations"])
    docs_connected = any(i["key"] in ("docusign", "dropbox_sign") and i["connected"] for i in settings["integrations"])
    ats_connected = any(i["key"] in ("greenhouse", "lever") and i["connected"] for i in settings["integrations"])

    steps: list[WizardStep] = [
        WizardStep(
            id="org-profile",
            title="Confirm your company profile",
            description="Legal name, timezone, fiscal year, primary locale. Used across every workflow + audit.",
            owner="Admin",
            cta_label="Open settings",
            cta_href="/app/settings",
            done=bool(settings["org"]["legal_name"]),
        ),
        WizardStep(
            id="brand",
            title="Set your brand",
            description="Accent color, voice tone, and wordmark. Keeps every email + doc on-brand.",
            owner="Admin",
            cta_label="Open settings",
            cta_href="/app/settings",
            done=bool(settings["brand"]["wordmark"] and settings["brand"]["wordmark"] != "F·P"),
        ),
        WizardStep(
            id="invite-team",
            title="Invite your first employees",
            description="The directory drives onboarding, performance, comp, and risk surfaces.",
            owner="HR",
            cta_label="Open directory",
            cta_href="/app/people",
            done=employees_total >= 3,
        ),
        WizardStep(
            id="messaging",
            title="Connect messaging (Slack + email)",
            description="Lets agents nudge managers and surface daily briefs.",
            owner="Admin",
            cta_label="Open integrations",
            cta_href="/app/settings",
            done=messaging_connected,
        ),
        WizardStep(
            id="payroll",
            title="Connect payroll",
            description="ADP or Gusto. Required for the workforce-finance forecasts and comp letters.",
            owner="HR / Finance",
            cta_label="Open integrations",
            cta_href="/app/settings",
            done=payroll_connected,
        ),
        WizardStep(
            id="benefits",
            title="Connect benefits provider",
            description="Guideline or Human Interest. Unlocks benefits answers in the AI Helpdesk.",
            owner="HR",
            cta_label="Open integrations",
            cta_href="/app/settings",
            done=benefits_connected,
        ),
        WizardStep(
            id="esign",
            title="Connect e-signature",
            description="DocuSign or Dropbox Sign. Used for offer letters + onboarding acknowledgements.",
            owner="HR",
            cta_label="Open integrations",
            cta_href="/app/settings",
            done=docs_connected,
        ),
        WizardStep(
            id="ats",
            title="Connect your ATS",
            description="Greenhouse or Lever. Syncs candidates into the Talent pipeline.",
            owner="HR / Recruiting",
            cta_label="Open integrations",
            cta_href="/app/settings",
            done=ats_connected,
        ),
        WizardStep(
            id="ingest-policies",
            title="Ingest policy library",
            description="Drop policies + SOPs into the Company Memory so the assistant can answer with citations.",
            owner="HR",
            cta_label="Open memory",
            cta_href="/app/memory",
            done=mem["total_documents"] >= 10,
        ),
        WizardStep(
            id="install-agents",
            title="Install your first AI agents",
            description="6 are built-in. Install Recognition, Learning, Benefits, or Ombudsman AI to extend the org.",
            owner="HR",
            cta_label="Open agent store",
            cta_href="/app/agent-store",
            done=installed_agents >= 6,
        ),
        WizardStep(
            id="first-onboarding",
            title="Run your first onboarding workflow",
            description="Use the Onboarding agent to auto-orchestrate a Day-1 → 90 day plan.",
            owner="HR",
            cta_label="Open onboarding",
            cta_href="/app/onboarding",
            done=packets_total >= 1,
        ),
        WizardStep(
            id="first-job",
            title="Post your first job",
            description="Use the Content Studio to draft a calm, bias-free JD.",
            owner="HR / Hiring",
            cta_label="Open content studio",
            cta_href="/app/content-studio",
            done=jobs_total >= 1,
        ),
    ]

    done = sum(1 for s in steps if s.done)
    total = len(steps)
    pct = round((done / total) * 100) if total else 0
    next_step = next((s for s in steps if not s.done), None)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [s.to_dict() for s in steps],
        "summary": {
            "done": done,
            "total": total,
            "completion_percent": pct,
            "next_step_id": next_step.id if next_step else None,
            "complete": done == total,
        },
    }
