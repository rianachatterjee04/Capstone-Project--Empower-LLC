"""Agent Marketplace — discoverable catalog of HR agents.

Wraps the existing AGENT_REGISTRY (the 6 built-in operators) with metadata
that turns it into a Store: category, description, capabilities, screenshot
hint, install status, and reviews placeholder.

Installable third-party agents are represented as catalog entries with
`built_in: false`; until they're actually wired they're disabled-on-install
so the UI clearly shows "available, not active." Once installed they appear
in the runtime registry.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

from app.services.agent_runtime import AGENT_REGISTRY


@dataclass
class AgentCatalogEntry:
    key: str
    name: str
    headline: str
    description: str
    category: str
    publisher: str = "Foundry People"
    capabilities: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    built_in: bool = True
    installable: bool = False
    rating: float = 4.8

    def to_dict(self, installed: bool) -> dict:
        return {
            **self.__dict__,
            "installed": installed,
        }


CATALOG: list[AgentCatalogEntry] = [
    AgentCatalogEntry(
        key="recruiting",
        name="Recruiting agent",
        headline="Screens candidates and keeps the pipeline moving.",
        description=(
            "Watches the recruiting pipeline. Proposes which unscored candidates to "
            "screen, which high-band candidates to schedule, and nudges hiring "
            "managers on aging offers."
        ),
        category="Hiring",
        capabilities=[
            "AI screening of unscored candidates",
            "Fast-track interview scheduling",
            "Offer aging nudges",
        ],
        triggers=["new candidate", "offer pending > 3 days", "manual run"],
    ),
    AgentCatalogEntry(
        key="onboarding",
        name="Onboarding agent",
        headline="Orchestrates Day-1 through 90 days automatically.",
        description=(
            "Generates personalized Day-1 plans, sends welcome emails, and tracks "
            "the canonical onboarding journey for every new hire."
        ),
        category="People",
        capabilities=[
            "Day-1 plan generation",
            "Welcome email drafting",
            "Buddy + equipment task assignment",
            "30/60/90 review reminders",
        ],
        triggers=["new hire created", "manual run"],
    ),
    AgentCatalogEntry(
        key="compliance",
        name="HR Compliance agent",
        headline="Closes the loop on cases and stale training.",
        description=(
            "Escalates aging ombudsman cases, flags employees with overdue "
            "compliance training, and proposes reporter updates."
        ),
        category="Compliance",
        capabilities=[
            "Case aging escalation",
            "Stale training detection",
            "Reporter status updates",
        ],
        triggers=["case > 30 days open", "training overdue", "manual run"],
    ),
    AgentCatalogEntry(
        key="performance",
        name="Performance agent",
        headline="Coaches managers through the review cycle.",
        description=(
            "Drafts balanced feedback, detects vague or biased language, builds "
            "calibration packets, and refreshes 9-box placement."
        ),
        category="Performance",
        capabilities=[
            "Balanced feedback rewriter",
            "Bias + vagueness detection",
            "Calibration packet generation",
            "9-box refresh",
        ],
        triggers=["cycle start", "manual run"],
    ),
    AgentCatalogEntry(
        key="compensation",
        name="Compensation agent",
        headline="Watches compa drift and models merit cycles.",
        description=(
            "Scans for under-paid high performers, flags band compression, and "
            "models cycle scenarios for finance review."
        ),
        category="Performance",
        capabilities=[
            "Compa-ratio drift scan",
            "Band compression detection",
            "Merit scenario modeling",
        ],
        triggers=["cycle start", "weekly", "manual run"],
    ),
    AgentCatalogEntry(
        key="workforce_planning",
        name="Workforce planning agent",
        headline="Forecasts staffing risk and payroll growth.",
        description=(
            "Surfaces departments likely to be understaffed in 45 days and models "
            "payroll growth over the planning horizon."
        ),
        category="Finance",
        capabilities=[
            "Understaffing forecast",
            "Payroll growth modeling",
            "Department-level load surfacing",
        ],
        triggers=["weekly", "manual run"],
    ),

    # Installable (not in runtime registry yet — clearly marked).
    AgentCatalogEntry(
        key="recognition",
        name="Recognition agent",
        headline="Detects moments worth celebrating.",
        description=(
            "Watches incident response, customer mentions, and project closeouts "
            "for high-impact wins, then proposes recognition + bonus pulses."
        ),
        category="Culture",
        capabilities=[
            "High-impact win detection",
            "Public recognition drafts",
            "Bonus pulse proposals",
        ],
        triggers=["incident response close", "weekly digest"],
        built_in=False,
        installable=True,
        rating=4.6,
    ),
    AgentCatalogEntry(
        key="learning",
        name="Learning agent",
        headline="Closes role-to-skill gaps automatically.",
        description=(
            "Watches the skills graph, detects gaps to the next role, and proposes "
            "personalised learning plans plus required compliance refreshers."
        ),
        category="Growth",
        capabilities=[
            "Skill gap detection",
            "Learning path proposals",
            "Compliance refresher scheduling",
        ],
        triggers=["skills graph drift", "cycle start"],
        built_in=False,
        installable=True,
        rating=4.7,
    ),
    AgentCatalogEntry(
        key="benefits",
        name="Benefits agent",
        headline="Answers benefit questions and flags utilization spikes.",
        description=(
            "Provides personalised plan explanations, surfaces qualifying life "
            "events, and flags utilization anomalies to HR."
        ),
        category="Operations",
        capabilities=[
            "Personalised plan explainers",
            "Qualifying life event detection",
            "Utilization spike alerts",
        ],
        triggers=["open enrollment", "QLE detected", "manual run"],
        built_in=False,
        installable=True,
        rating=4.5,
    ),
    AgentCatalogEntry(
        key="ombudsman_ai",
        name="Ombudsman AI",
        headline="Confidential first-pass on every report.",
        description=(
            "Categorises and severity-scores new ombudsman submissions, drafts "
            "case summaries for HR + legal, and surfaces retaliation risk signals."
        ),
        category="Compliance",
        capabilities=[
            "Auto-categorisation",
            "Severity scoring",
            "Risk signal surfacing",
        ],
        triggers=["new case submitted", "weekly digest"],
        built_in=False,
        installable=True,
        rating=4.9,
    ),
]


# ---------------------------------------------------------------------------
_lock = threading.RLock()
_installed: dict[str, set[str]] = {}    # org_id -> set of installed third-party keys


def _ensure_installed(org_id: str) -> set[str]:
    with _lock:
        return _installed.setdefault(org_id, set())


def list_catalog(org_id: str) -> list[dict]:
    runtime_keys = set(AGENT_REGISTRY.keys())
    org_installed = _ensure_installed(org_id)
    out: list[dict] = []
    for entry in CATALOG:
        installed = entry.key in runtime_keys or entry.key in org_installed
        out.append(entry.to_dict(installed=installed))
    return out


def categories() -> list[str]:
    return sorted({e.category for e in CATALOG})


def install(org_id: str, key: str) -> Optional[dict]:
    entry = next((e for e in CATALOG if e.key == key), None)
    if not entry:
        return None
    if not entry.installable and not entry.built_in:
        return None
    with _lock:
        _ensure_installed(org_id).add(key)
    return entry.to_dict(installed=True)


def uninstall(org_id: str, key: str) -> bool:
    with _lock:
        if key in _ensure_installed(org_id):
            _ensure_installed(org_id).remove(key)
            return True
    return False
