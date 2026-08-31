"""Settings & configuration hub.

Consolidates the org's configuration into a single service:
  - org profile (legal name, display name, domain, timezone, fiscal year start)
  - brand (accent, logo wordmark, voice)
  - integrations (Slack, Email, ADP, QuickBooks, Guideline, DocuSign, Greenhouse, Lever)
  - automation rules (which agents auto-run on which triggers)
  - security & permissions (SSO, MFA, audit retention)

In-memory per org for the demo. Production swaps in a Postgres-backed store
behind the exact same API surface.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
@dataclass
class OrgProfile:
    legal_name: str = "Foundry People"
    display_name: str = "Foundry"
    domain: str = "foundrypeople.com"
    timezone: str = "America/Los_Angeles"
    fiscal_year_start: str = "01-01"
    primary_locale: str = "en-US"
    headquarters: str = "San Francisco, CA"


@dataclass
class Brand:
    accent: str = "#1F1F25"
    canvas: str = "#F7F6F2"
    wordmark: str = "F·P"
    tone_of_voice: str = "Calm, premium, specific. Avoid superlatives."


@dataclass
class IntegrationStatus:
    key: str
    name: str
    category: str
    connected: bool = False
    note: Optional[str] = None


@dataclass
class AutomationRule:
    id: str
    label: str
    description: str
    trigger: str           # e.g. "new_hire_created", "cycle_started"
    agent: str             # which built-in agent picks it up
    enabled: bool = True
    requires_approval: bool = True


@dataclass
class SecurityPosture:
    sso_provider: str = "Email magic link"
    mfa_required: bool = True
    audit_retention_years: int = 7
    data_residency: str = "US-West"
    soc2_status: str = "Type II controls active"
    last_security_review: str = "2026-04-02"


@dataclass
class OrgSettings:
    org: OrgProfile = field(default_factory=OrgProfile)
    brand: Brand = field(default_factory=Brand)
    integrations: list[IntegrationStatus] = field(default_factory=list)
    automations: list[AutomationRule] = field(default_factory=list)
    security: SecurityPosture = field(default_factory=SecurityPosture)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_DEFAULT_INTEGRATIONS = [
    IntegrationStatus("slack", "Slack", "messaging", True, "Notifications + agent nudges enabled."),
    IntegrationStatus("email", "Email (SMTP)", "messaging", True, "Transactional + digest emails."),
    IntegrationStatus("docusign", "DocuSign", "documents", False, "Offer letters + acknowledgements."),
    IntegrationStatus("dropbox_sign", "Dropbox Sign", "documents", True, "Onboarding e-sign default."),
    IntegrationStatus("adp", "ADP", "payroll", False, "Payroll run + tax filings."),
    IntegrationStatus("gusto", "Gusto", "payroll", False, "Alternative payroll provider."),
    IntegrationStatus("quickbooks", "QuickBooks Online", "finance", False, "GL posting for payroll runs."),
    IntegrationStatus("guideline", "Guideline 401(k)", "benefits", True, "Retirement plan sync."),
    IntegrationStatus("human_interest", "Human Interest", "benefits", False, "Alternative retirement plan."),
    IntegrationStatus("greenhouse", "Greenhouse ATS", "hiring", False, "Two-way candidate sync."),
    IntegrationStatus("lever", "Lever ATS", "hiring", True, "Two-way candidate sync."),
    IntegrationStatus("openai", "OpenAI", "ai", False, "LLM completion + embeddings. Set OPENAI_API_KEY."),
]


def _default_automations() -> list[AutomationRule]:
    return [
        AutomationRule(
            id="auto-onboard-1",
            label="Auto-orchestrate onboarding for every new hire",
            description="When an employee is invited, the Onboarding agent generates the canonical Day-1 → 90 day task chain.",
            trigger="employee.invited",
            agent="onboarding",
            enabled=True,
            requires_approval=False,
        ),
        AutomationRule(
            id="auto-recruit-1",
            label="Auto-screen new candidates",
            description="When a candidate is added, the Recruiting agent runs the AI screener and writes a score.",
            trigger="candidate.created",
            agent="recruiting",
            enabled=True,
            requires_approval=False,
        ),
        AutomationRule(
            id="auto-compliance-1",
            label="Escalate aging ombudsman cases",
            description="When a case is open > 14 days, the Compliance agent escalates and proposes a reporter update.",
            trigger="case.aging",
            agent="compliance",
            enabled=True,
            requires_approval=True,
        ),
        AutomationRule(
            id="auto-recognition-1",
            label="Detect high-impact wins for recognition",
            description="When an incident is resolved with measurable customer impact, the Recognition agent proposes a public praise + bonus pulse.",
            trigger="incident.resolved",
            agent="recognition",
            enabled=False,
            requires_approval=True,
        ),
        AutomationRule(
            id="auto-perf-1",
            label="Flag vague or biased feedback in reviews",
            description="When a manager submits review text, the Performance agent inspects it inline before delivery.",
            trigger="review.submitted",
            agent="performance",
            enabled=True,
            requires_approval=False,
        ),
        AutomationRule(
            id="auto-comp-1",
            label="Weekly compa-ratio drift scan",
            description="The Compensation agent scans for under-paid high performers and band compression.",
            trigger="weekly",
            agent="compensation",
            enabled=True,
            requires_approval=True,
        ),
        AutomationRule(
            id="auto-plan-1",
            label="Quarterly workforce planning forecast",
            description="The Workforce Planning agent forecasts hiring need and payroll impact each quarter.",
            trigger="quarterly",
            agent="workforce_planning",
            enabled=True,
            requires_approval=True,
        ),
    ]


# ---------------------------------------------------------------------------
_lock = threading.RLock()
_store: dict[str, OrgSettings] = {}


def _ensure(org_id: str) -> OrgSettings:
    with _lock:
        s = _store.get(org_id)
        if s is None:
            s = OrgSettings(
                integrations=list(_DEFAULT_INTEGRATIONS),
                automations=_default_automations(),
            )
            _store[org_id] = s
        return s


def get_settings(org_id: str) -> dict:
    s = _ensure(org_id)
    return {
        "org": asdict(s.org),
        "brand": asdict(s.brand),
        "integrations": [asdict(i) for i in s.integrations],
        "automations": [asdict(a) for a in s.automations],
        "security": asdict(s.security),
        "updated_at": s.updated_at,
        "categories": sorted({i.category for i in s.integrations}),
    }


def update_org(org_id: str, payload: dict) -> dict:
    s = _ensure(org_id)
    with _lock:
        for k, v in payload.items():
            if hasattr(s.org, k):
                setattr(s.org, k, v)
        s.updated_at = datetime.now(timezone.utc).isoformat()
    return get_settings(org_id)


def update_brand(org_id: str, payload: dict) -> dict:
    s = _ensure(org_id)
    with _lock:
        for k, v in payload.items():
            if hasattr(s.brand, k):
                setattr(s.brand, k, v)
        s.updated_at = datetime.now(timezone.utc).isoformat()
    return get_settings(org_id)


def toggle_integration(org_id: str, key: str, connected: Optional[bool] = None) -> Optional[dict]:
    s = _ensure(org_id)
    with _lock:
        for i in s.integrations:
            if i.key == key:
                i.connected = connected if connected is not None else (not i.connected)
                s.updated_at = datetime.now(timezone.utc).isoformat()
                return asdict(i)
    return None


def toggle_automation(org_id: str, rule_id: str, enabled: Optional[bool] = None) -> Optional[dict]:
    s = _ensure(org_id)
    with _lock:
        for a in s.automations:
            if a.id == rule_id:
                a.enabled = enabled if enabled is not None else (not a.enabled)
                s.updated_at = datetime.now(timezone.utc).isoformat()
                return asdict(a)
    return None


def update_security(org_id: str, payload: dict) -> dict:
    s = _ensure(org_id)
    with _lock:
        for k, v in payload.items():
            if hasattr(s.security, k):
                setattr(s.security, k, v)
        s.updated_at = datetime.now(timezone.utc).isoformat()
    return get_settings(org_id)
