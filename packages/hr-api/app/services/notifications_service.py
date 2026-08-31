"""Notifications service.

Separate from the Inbox (which is "what needs you, ranked by the CPO").
Notifications are proactive alerts grouped by topic, with mark-as-read,
mark-all-read, and snooze.

In-process store; mirrors what a notifications table would look like.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class Notification:
    id: str
    title: str
    detail: str
    topic: str               # hiring | compliance | risk | learning | recognition | system
    severity: str = "info"    # info | warn | danger | success
    cta_label: str = "Open"
    cta_href: str = "/app"
    actor: Optional[str] = None
    read: bool = False
    snoozed_until: Optional[str] = None
    # True for the example alerts this service seeds into a new tenant. A
    # notification raised by a real event leaves this False.
    is_sample: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return self.__dict__


_lock = threading.RLock()
_store: dict[str, list[Notification]] = {}
_seeded: set[str] = set()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _seed(org_id: str) -> None:
    now = datetime.now(timezone.utc)

    # EVERY NOTIFICATION BELOW IS SEEDED.
    #
    # The feed led with "Avery Chen flagged high attrition risk · WORKFORCE
    # RISK AGENT · Compa-ratio below 0.85 (under-paid vs. band midpoint). No
    # raise in 22 months. · 2H AGO" — a claim about a named person's pay,
    # attributed to an agent, timestamped two hours ago, for an organisation
    # where that person does not work. Another said "2 high-severity ombudsman"
    # while the ombudsman page correctly showed zero cases: two screens
    # disagreeing about the same tenant.
    #
    # A notification is a claim that something HAPPENED. These are marked so
    # the page can say they did not.
    def _t(**kwargs) -> Notification:
        kwargs.setdefault("is_sample", True)
        return Notification(id=str(uuid.uuid4()), **kwargs)

    _store[org_id] = [
        _t(
            title="Avery Chen flagged high attrition risk",
            detail="Compa-ratio below 0.85 (under-paid vs. band midpoint). No raise in 22 months.",
            topic="risk", severity="danger",
            cta_label="Open risk", cta_href="/app/risk",
            actor="Workforce risk agent",
            created_at=_iso(now - timedelta(hours=2)),
        ),
        _t(
            title="2 high-severity ombudsman cases still open",
            detail="Both have been open > 30 days. Reporter updates due this week.",
            topic="compliance", severity="danger",
            cta_label="Open ombudsman", cta_href="/app/ombudsman",
            created_at=_iso(now - timedelta(hours=5)),
        ),
        _t(
            title="3 SOC 2 trainings overdue",
            detail="Send reminders this week; escalate week 2.",
            topic="compliance", severity="warn",
            cta_label="Open compliance", cta_href="/app/compliance",
            actor="Compliance agent",
            created_at=_iso(now - timedelta(hours=9)),
        ),
        _t(
            title="Pipeline thin: 4 candidates across 4 open reqs",
            detail="Healthy SMB pipeline is ~5 qualified candidates per role.",
            topic="hiring", severity="warn",
            cta_label="Open talent", cta_href="/app/talent",
            actor="Recruiting agent",
            created_at=_iso(now - timedelta(hours=18)),
        ),
        _t(
            title="Diego Marin offer pending finance approval",
            detail="Loop in CFO before week-end to avoid cycle slip.",
            topic="hiring", severity="info",
            cta_label="Open CRM", cta_href="/app/crm",
            created_at=_iso(now - timedelta(days=1)),
        ),
        _t(
            title="Q2 review cycle calibration on Aug 18",
            detail="Cross-team rater drift review. Add to your calendar.",
            topic="system", severity="info",
            cta_label="Open performance", cta_href="/app/performance",
            created_at=_iso(now - timedelta(days=2)),
        ),
        _t(
            title="Recognition opportunity: Emily Stone",
            detail="Customer-saving incident response last week. Public recognition + bonus pulse.",
            topic="recognition", severity="success",
            cta_label="Open recognition", cta_href="/app/recognition",
            actor="Recognition agent",
            created_at=_iso(now - timedelta(days=3)),
        ),
        _t(
            title="New learning path proposed for Design team",
            detail="2 designers added new tools; skills graph refreshed.",
            topic="learning", severity="info",
            cta_label="Open learning", cta_href="/app/learning",
            created_at=_iso(now - timedelta(days=4)),
        ),
        _t(
            title="Welcome message sent to Riley Singh",
            detail="Onboarding agent sent the Day-1 plan + manager intro.",
            topic="system", severity="success",
            actor="Onboarding agent",
            cta_label="Open onboarding", cta_href="/app/onboarding",
            read=True,
            created_at=_iso(now - timedelta(days=5)),
        ),
    ]


def _ensure(org_id: str) -> list[Notification]:
    with _lock:
        if org_id not in _seeded:
            _seed(org_id)
            _seeded.add(org_id)
        return _store.setdefault(org_id, [])


def list_notifications(org_id: str, *, topic: Optional[str] = None, unread_only: bool = False) -> dict:
    rows = _ensure(org_id)
    # Strip rows whose snooze hasn't elapsed
    now = datetime.now(timezone.utc)
    visible: list[Notification] = []
    for n in rows:
        if n.snoozed_until:
            try:
                if datetime.fromisoformat(n.snoozed_until) > now:
                    continue
            except Exception:
                pass
        visible.append(n)

    if topic:
        visible = [n for n in visible if n.topic == topic]
    if unread_only:
        visible = [n for n in visible if not n.read]

    by_topic: dict[str, int] = {}
    unread = 0
    for n in visible:
        by_topic[n.topic] = by_topic.get(n.topic, 0) + 1
        if not n.read:
            unread += 1

    samples = sum(1 for n in visible if getattr(n, "is_sample", False))
    return {
        "items": [n.to_dict() for n in visible],
        "counts": {"total": len(visible), "unread": unread, "by_topic": by_topic},
        "topics": ["hiring", "compliance", "risk", "learning", "recognition", "system"],
        "provenance": {
            "sample_notifications": samples,
            "all_sample": bool(visible) and samples == len(visible),
            "note": (
                "These are example alerts shipped with the product. Nothing here "
                "was triggered by an event in your organisation."
                if visible and samples == len(visible) else None
            ),
        },
    }


def mark_read(org_id: str, notification_id: str, read: bool = True) -> Optional[dict]:
    rows = _ensure(org_id)
    with _lock:
        for n in rows:
            if n.id == notification_id:
                n.read = read
                return n.to_dict()
    return None


def mark_all_read(org_id: str) -> int:
    rows = _ensure(org_id)
    n = 0
    with _lock:
        for r in rows:
            if not r.read:
                r.read = True
                n += 1
    return n


def snooze(org_id: str, notification_id: str, hours: int = 24) -> Optional[dict]:
    rows = _ensure(org_id)
    with _lock:
        for n in rows:
            if n.id == notification_id:
                n.snoozed_until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
                return n.to_dict()
    return None


def push(org_id: str, payload: dict) -> dict:
    rows = _ensure(org_id)
    n = Notification(
        id=str(uuid.uuid4()),
        title=str(payload.get("title") or "Notification"),
        detail=str(payload.get("detail") or ""),
        topic=str(payload.get("topic") or "system"),
        severity=str(payload.get("severity") or "info"),
        cta_label=str(payload.get("cta_label") or "Open"),
        cta_href=str(payload.get("cta_href") or "/app"),
        actor=payload.get("actor"),
    )
    with _lock:
        rows.insert(0, n)
    return n.to_dict()
