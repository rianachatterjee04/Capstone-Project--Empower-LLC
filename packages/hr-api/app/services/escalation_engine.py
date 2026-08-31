from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.db.models import Case, EscalationRule, Escalation, AuditEvent

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

def _sev(s: str) -> int:
    return SEVERITY_ORDER.get((s or "").lower(), 0)

async def ensure_case_escalations(db: AsyncSession, org_id: UUID) -> int:
    """Creates escalations for cases based on escalation_rules and due_at timers."""
    created = 0
    # Load active rules for cases
    rules = (await db.execute(select(EscalationRule).where(
        EscalationRule.org_id == org_id,
        EscalationRule.entity_type == "case",
        EscalationRule.is_active == True,
    ))).scalars().all()

    if not rules:
        return 0

    cases = (await db.execute(select(Case).where(Case.org_id == org_id, Case.status.in_(["reported","assigned"])))).scalars().all()
    now = datetime.now(timezone.utc)

    for c in cases:
        for r in rules:
            # severity floor check
            if r.severity_floor and _sev(c.severity) < _sev(r.severity_floor):
                continue
            # category check inside condition_dsl (optional)
            cond = r.condition_dsl or {}
            cat_in = (cond.get("category_in") or [])
            if cat_in and (c.category or "").lower() not in [x.lower() for x in cat_in]:
                continue

            # Insert escalation if not exists
            due_at = c.created_at + timedelta(minutes=int(r.sla_minutes))
            q = text("""
              insert into public.escalations(org_id, entity_type, entity_id, rule_id, level, status, due_at)
              values (:org_id, 'case', :entity_id, :rule_id, 0, 'active', :due_at)
              on conflict (org_id, entity_type, entity_id, rule_id) do nothing
              returning id
            """)
            res = await db.execute(q, {"org_id": str(org_id), "entity_id": str(c.id), "rule_id": str(r.id), "due_at": due_at})
            row = res.first()
            if row:
                created += 1
                db.add(AuditEvent(
                    org_id=org_id,
                    actor_user_id=None,
                    actor_role="system",
                    event_type="escalation.created",
                    entity_type="escalation",
                    entity_id=row[0],
                    payload={"entity_type":"case","case_id": str(c.id), "rule_id": str(r.id), "due_at": due_at.isoformat()},
                ))
    await db.commit()
    return created

async def escalate_overdue(db: AsyncSession, org_id: UUID) -> int:
    """Bumps escalation level when overdue. Routing/notifications are stubbed (hook to email/push/webhooks)."""
    now = datetime.now(timezone.utc)
    q = text("""
      update public.escalations
      set level = level + 1, last_notified_at = now()
      where org_id = :org_id and status = 'active' and due_at < now()
      returning id, level
    """)
    res = await db.execute(q, {"org_id": str(org_id)})
    rows = res.fetchall()
    for (eid, level) in rows:
        db.add(AuditEvent(
            org_id=org_id,
            actor_user_id=None,
            actor_role="system",
            event_type="escalation.bumped",
            entity_type="escalation",
            entity_id=eid,
            payload={"new_level": int(level)},
        ))
    await db.commit()
    return len(rows)
