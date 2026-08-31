"""Workflow Automations — visual trigger → action builder.

This is the foundation under "agentic" — the user-facing way to wire an
event ("burnout signal raised") to a chain of actions ("draft 1:1 talk
track for manager, schedule 30m, notify HRBP").

The service maintains:
  - A **trigger taxonomy** (hire, milestone, risk signal, schedule, manual)
  - An **action taxonomy** (notify, draft email, schedule meeting, escalate,
    create task, change status, run AI agent)
  - A library of **automations** (each: trigger + filters + ordered actions)
  - A library of **pre-built templates** the user can install with one click
  - **Run history** so the user sees what fired, what succeeded, what
    erred — defensible audit trail.

The runtime here just records intent; the actual execution piggy-backs on
the existing agent runtime. This service is the configuration + history
surface.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Taxonomies
# ---------------------------------------------------------------------------
TRIGGERS = [
    {"key": "hire.new",                "label": "New hire signed",          "category": "hire",     "schedule": False},
    {"key": "hire.offer_accepted",     "label": "Offer accepted",           "category": "hire",     "schedule": False},
    {"key": "onboarding.day_1",        "label": "First day arrived",        "category": "milestone","schedule": False},
    {"key": "onboarding.day_30",       "label": "30 day milestone",         "category": "milestone","schedule": False},
    {"key": "onboarding.day_90",       "label": "90 day milestone",         "category": "milestone","schedule": False},
    {"key": "perf.review_overdue",     "label": "Performance review overdue","category": "milestone","schedule": False},
    {"key": "risk.burnout",            "label": "Burnout signal raised",    "category": "risk",     "schedule": False},
    {"key": "risk.attrition",          "label": "Attrition risk raised",    "category": "risk",     "schedule": False},
    {"key": "risk.compliance",         "label": "Compliance gap detected",  "category": "risk",     "schedule": False},
    {"key": "hiring.bottleneck",       "label": "Hiring stage bottleneck",  "category": "risk",     "schedule": False},
    {"key": "comp.compression",        "label": "Pay compression detected", "category": "risk",     "schedule": False},
    {"key": "ombudsman.case_opened",   "label": "Ombudsman case opened",    "category": "risk",     "schedule": False},
    {"key": "schedule.daily",          "label": "Every day",                "category": "schedule", "schedule": True},
    {"key": "schedule.weekly",         "label": "Every week",               "category": "schedule", "schedule": True},
    {"key": "schedule.monthly",        "label": "Every month",              "category": "schedule", "schedule": True},
    {"key": "manual",                  "label": "Manual trigger",           "category": "manual",   "schedule": False},
]

ACTIONS = [
    {"key": "notify.slack",       "label": "Send Slack message",          "category": "notify"},
    {"key": "notify.email",       "label": "Send email",                  "category": "notify"},
    {"key": "notify.inbox",       "label": "Drop into approvals inbox",   "category": "notify"},
    {"key": "draft.outreach",     "label": "AI: draft candidate outreach","category": "draft"},
    {"key": "draft.review",       "label": "AI: draft performance review summary", "category": "draft"},
    {"key": "draft.talk_track",   "label": "AI: draft manager talk track","category": "draft"},
    {"key": "schedule.meeting",   "label": "Schedule 1:1 meeting",        "category": "schedule"},
    {"key": "escalate.hrbp",      "label": "Escalate to HRBP",            "category": "escalate"},
    {"key": "escalate.legal",     "label": "Escalate to Legal",           "category": "escalate"},
    {"key": "task.create",        "label": "Create task in Work Hub",     "category": "task"},
    {"key": "status.update",      "label": "Update record status",        "category": "task"},
    {"key": "agent.run",          "label": "Run AI agent",                "category": "ai"},
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class AutomationAction:
    key: str
    label: str
    params: dict = field(default_factory=dict)


@dataclass
class Automation:
    id: str
    org_id: str
    name: str
    description: str = ""
    trigger_key: str = "manual"
    filters: dict = field(default_factory=dict)   # eg {"severity": "critical"}
    actions: list[AutomationAction] = field(default_factory=list)
    enabled: bool = True
    template_id: Optional[str] = None
    runs_total: int = 0
    runs_success: int = 0
    runs_failed: int = 0
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            **self.__dict__,
            "actions": [a.__dict__ for a in self.actions],
        }


@dataclass
class AutomationRun:
    id: str
    org_id: str
    automation_id: str
    automation_name: str
    triggered_at: str
    trigger_key: str
    payload: dict
    actions_attempted: int
    actions_succeeded: int
    status: str            # success | partial | failed
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# Pre-built templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "id":          "burnout-response",
        "name":        "Burnout signal → manager talk track + 1:1",
        "description": "When the risk engine flags burnout, draft a talk track for the manager and schedule a 30-min 1:1.",
        "trigger_key": "risk.burnout",
        "filters":     {"severity": "critical|alert"},
        "actions": [
            {"key": "draft.talk_track", "label": "Draft manager talk track"},
            {"key": "schedule.meeting", "label": "Schedule 1:1 (30m)"},
            {"key": "notify.inbox",     "label": "Drop into manager's inbox"},
        ],
    },
    {
        "id":          "new-hire-day-1",
        "name":        "New hire arrives → onboarding orchestrator",
        "description": "On day 1, kick off the 30/60/90 plan, assign a buddy, and notify the team.",
        "trigger_key": "onboarding.day_1",
        "filters":     {},
        "actions": [
            {"key": "agent.run",     "label": "Run onboarding orchestrator agent"},
            {"key": "task.create",   "label": "Create 30/60/90 task list"},
            {"key": "notify.slack",  "label": "Announce in #welcome"},
        ],
    },
    {
        "id":          "review-overdue-nudge",
        "name":        "Review overdue → manager nudge",
        "description": "Nudge the manager 24h before a review goes stale; escalate after 72h.",
        "trigger_key": "perf.review_overdue",
        "filters":     {},
        "actions": [
            {"key": "notify.slack",  "label": "Slack DM to manager"},
            {"key": "notify.inbox",  "label": "Inbox card with one-click write"},
        ],
    },
    {
        "id":          "bottleneck-clear",
        "name":        "Hiring bottleneck → recruiter sweep",
        "description": "When a stage stalls past target, draft re-engagement outreach for affected candidates.",
        "trigger_key": "hiring.bottleneck",
        "filters":     {"severity": "alert|critical"},
        "actions": [
            {"key": "draft.outreach", "label": "Draft re-engagement outreach"},
            {"key": "notify.inbox",   "label": "Drop into recruiter inbox"},
        ],
    },
    {
        "id":          "ombudsman-intake",
        "name":        "Ombudsman case opened → triage",
        "description": "On case intake, AI risk-categorises and drafts an investigation plan for compliance.",
        "trigger_key": "ombudsman.case_opened",
        "filters":     {},
        "actions": [
            {"key": "agent.run",        "label": "Run ombudsman intake agent"},
            {"key": "escalate.hrbp",    "label": "Notify HRBP (no reporter identity)"},
            {"key": "task.create",      "label": "Create investigation task"},
        ],
    },
    {
        "id":          "pay-compression",
        "name":        "Pay compression flagged → comp prep",
        "description": "Pre-build a comp-adjustment proposal for the next review cycle.",
        "trigger_key": "comp.compression",
        "filters":     {},
        "actions": [
            {"key": "agent.run",        "label": "Run comp prep agent"},
            {"key": "notify.inbox",     "label": "Notify HRBP + manager"},
        ],
    },
    {
        "id":          "weekly-exec-brief",
        "name":        "Every Monday → Executive Brief",
        "description": "Run the executive brief agent and email it to the leadership team.",
        "trigger_key": "schedule.weekly",
        "filters":     {"day_of_week": "monday", "time": "06:30"},
        "actions": [
            {"key": "agent.run",     "label": "Generate executive brief"},
            {"key": "notify.email",  "label": "Email leadership team"},
        ],
    },
    {
        "id":          "compliance-sweep",
        "name":        "Monthly → policy acknowledgment sweep",
        "description": "Audit policy acknowledgments and nudge laggards.",
        "trigger_key": "schedule.monthly",
        "filters":     {"day_of_month": "1"},
        "actions": [
            {"key": "agent.run",     "label": "Run compliance sweep agent"},
            {"key": "notify.email",  "label": "Email laggards"},
            {"key": "notify.inbox",  "label": "Drop summary into compliance inbox"},
        ],
    },
]


# ---------------------------------------------------------------------------
# In-process stores
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_automations: dict[str, dict[str, Automation]] = {}
_runs: dict[str, list[AutomationRun]] = {}


def _ensure_demo_seed(org_id: str) -> None:
    with _lock:
        if org_id not in _automations:
            _automations[org_id] = {}
            # Install three default templates so the demo isn't empty.
            for tpl in TEMPLATES[:3]:
                install_template(org_id, tpl["id"], _no_seed=True)
        if org_id not in _runs:
            _runs[org_id] = []


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------
def list_automations(org_id: str) -> list[Automation]:
    _ensure_demo_seed(org_id)
    with _lock:
        items = list(_automations.get(org_id, {}).values())
    items.sort(key=lambda a: (-1 if a.enabled else 0, a.name.lower()))
    return items


def get_automation(org_id: str, automation_id: str) -> Optional[Automation]:
    _ensure_demo_seed(org_id)
    return _automations.get(org_id, {}).get(automation_id)


def _actions_from(raw) -> list["AutomationAction"]:
    """Build actions from a caller-supplied list, refusing an unusable one.

    This was a comprehension doing x["key"] over whatever the caller sent, so
    POSTing an action without a key raised KeyError and the endpoint answered
    500 with the single word 'key' as its explanation. Creating an automation
    with a malformed action is the caller's mistake to fix, and they can only
    fix it if we say which action and which field.
    """
    built: list[AutomationAction] = []
    for i, x in enumerate(raw or []):
        if not isinstance(x, dict):
            raise HTTPException(422, detail=f"action {i} must be an object, got {type(x).__name__}")
        if not x.get("key"):
            raise HTTPException(
                422,
                detail=(f"action {i} has no 'key' -- an automation action must say what "
                        f"to do. Got fields: {sorted(x) or 'none'}"),
            )
        built.append(AutomationAction(key=x["key"], label=x.get("label", ""),
                                      params=x.get("params") or {}))
    return built


def create_automation(
    org_id: str,
    *,
    name: str,
    description: str,
    trigger_key: str,
    filters: dict,
    actions: list[dict],
    enabled: bool = True,
    template_id: Optional[str] = None,
) -> Automation:
    _ensure_demo_seed(org_id)
    a = Automation(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name=name,
        description=description,
        trigger_key=trigger_key,
        filters=filters or {},
        actions=_actions_from(actions),
        enabled=enabled,
        template_id=template_id,
    )
    with _lock:
        _automations.setdefault(org_id, {})[a.id] = a
    return a


def update_automation(org_id: str, automation_id: str, payload: dict) -> Optional[Automation]:
    _ensure_demo_seed(org_id)
    with _lock:
        a = _automations.get(org_id, {}).get(automation_id)
        if not a:
            return None
        if "name" in payload:
            a.name = str(payload["name"]).strip() or a.name
        if "description" in payload:
            a.description = str(payload["description"])
        if "trigger_key" in payload:
            a.trigger_key = str(payload["trigger_key"])
        if "filters" in payload:
            a.filters = payload["filters"] or {}
        if "actions" in payload:
            a.actions = _actions_from(payload["actions"])
        if "enabled" in payload:
            a.enabled = bool(payload["enabled"])
        a.updated_at = datetime.now(timezone.utc).isoformat()
        return a


def delete_automation(org_id: str, automation_id: str) -> bool:
    _ensure_demo_seed(org_id)
    with _lock:
        if automation_id in _automations.get(org_id, {}):
            del _automations[org_id][automation_id]
            return True
    return False


def install_template(org_id: str, template_id: str, *, _no_seed: bool = False) -> Optional[Automation]:
    if not _no_seed:
        _ensure_demo_seed(org_id)
    tpl = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        return None
    return create_automation(
        org_id,
        name=tpl["name"],
        description=tpl["description"],
        trigger_key=tpl["trigger_key"],
        filters=tpl["filters"],
        actions=tpl["actions"],
        template_id=tpl["id"],
    )


def list_runs(org_id: str, *, limit: int = 50) -> list[AutomationRun]:
    _ensure_demo_seed(org_id)
    with _lock:
        items = list(_runs.get(org_id, []))
    items.sort(key=lambda r: r.triggered_at, reverse=True)
    return items[:limit]


def trigger_automation(org_id: str, automation_id: str, payload: dict) -> Optional[AutomationRun]:
    """Manually fire an automation — the demo path. Real triggers wire to
    audit events / risk signals / scheduler."""
    _ensure_demo_seed(org_id)
    a = get_automation(org_id, automation_id)
    if not a:
        return None
    log: list[str] = []
    succeeded = 0
    for act in a.actions:
        # Demo execution: just record intent.
        log.append(f"action='{act.key}' (label={act.label}) — recorded")
        succeeded += 1
    status = "success" if succeeded == len(a.actions) else "partial" if succeeded > 0 else "failed"
    run = AutomationRun(
        id=str(uuid.uuid4()),
        org_id=org_id,
        automation_id=a.id,
        automation_name=a.name,
        triggered_at=datetime.now(timezone.utc).isoformat(),
        trigger_key=a.trigger_key,
        payload=payload or {},
        actions_attempted=len(a.actions),
        actions_succeeded=succeeded,
        status=status,
        log=log,
    )
    with _lock:
        a.runs_total += 1
        if status == "success":
            a.runs_success += 1
        elif status == "failed":
            a.runs_failed += 1
        a.last_run_at = run.triggered_at
        a.last_run_status = status
        _runs.setdefault(org_id, []).append(run)
    return run
