from __future__ import annotations
from datetime import datetime, timedelta

# Simple policy. In production, store per-org escalation rules and allow AI to propose updates.
ESCALATION_WINDOWS = {
    "low": timedelta(days=7),
    "medium": timedelta(days=3),
    "high": timedelta(hours=24),
    "critical": timedelta(hours=4),
}

def should_escalate(severity: str, last_action_at: datetime) -> bool:
    window = ESCALATION_WINDOWS.get(severity, timedelta(days=3))
    return datetime.utcnow() - last_action_at > window
