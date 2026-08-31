"""Unified approvals center.

Today the org has 5+ approval surfaces (PTO, comp letter, onboarding packet,
offer, agent action, expense, etc.). The Approvals Center collapses them
into a single queue with consistent tones, due dates, and one-click actions.

The service intentionally reads from live tables when available and from
in-process stores (agents) otherwise — so it works the day a new approval
type lands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_runtime import list_runs


@dataclass
class Approval:
    id: str
    kind: str            # pto | onboarding_packet | offer | agent_action | comp_letter | expense
    title: str
    detail: str
    requested_by: Optional[str] = None
    requires_role: str = "manager"   # who can approve
    severity: str = "normal"         # urgent | normal | low
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cta_label: str = "Review"
    cta_href: str = "/app"
    approve_endpoint: Optional[str] = None
    deny_endpoint: Optional[str] = None
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
async def _rows(db: AsyncSession, sql: str, params: dict) -> list[dict]:
    try:
        res = await db.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()]
    except Exception:
        return []


async def _scalar(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        row = (await db.execute(text(sql), params)).first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


async def list_approvals(db: AsyncSession, org_id: str, *, kind: Optional[str] = None) -> dict:
    out: list[Approval] = []

    # 1. PTO requests
    pto_rows = await _rows(
        db,
        """
        select r.id::text as id, r.start_date, r.end_date, r.reason, r.status,
               e.legal_name as requested_by, r.created_at
        from public.pto_requests r
        left join public.employees e on e.id = r.employee_id
        where r.org_id=:org and r.status='pending'
        order by r.created_at desc
        """,
        {"org": org_id},
    )
    for p in pto_rows:
        out.append(Approval(
            id=f"pto-{p['id']}",
            kind="pto",
            title=f"PTO · {p.get('requested_by') or 'Employee'} · {p['start_date']} → {p['end_date']}",
            detail=p.get("reason") or "—",
            requested_by=p.get("requested_by"),
            requires_role="manager",
            severity="urgent" if _within_days(p.get("start_date"), 3) else "normal",
            created_at=str(p.get("created_at") or datetime.now(timezone.utc).isoformat()),
            cta_label="Open PTO",
            cta_href=f"/app/pto",
            approve_endpoint=f"/pto/{p['id']}/approve",
            deny_endpoint=f"/pto/{p['id']}/deny",
            payload={"start_date": str(p["start_date"]), "end_date": str(p["end_date"])},
        ))

    # 2. Onboarding packets ready for HR verification / activation
    pk_rows = await _rows(
        db,
        """
        select id::text as id, employee_id::text as employee_id, status, created_at
        from public.onboarding_packets
        where org_id=:org and status in ('completed','verified')
        """,
        {"org": org_id},
    )
    for p in pk_rows:
        is_verify = p["status"] == "completed"
        out.append(Approval(
            id=f"packet-{p['id']}-{p['status']}",
            kind="onboarding_packet",
            title=f"Onboarding packet · {'verify' if is_verify else 'activate'}",
            detail=f"Packet {p['id'][:8]} is {p['status']}.",
            requires_role="hr",
            severity="normal",
            created_at=str(p["created_at"]),
            cta_label="Open packet",
            cta_href="/app/onboarding",
            approve_endpoint=f"/onboarding/packets/{p['id']}/{'verify' if is_verify else 'activate'}",
        ))

    # 3. Offers — candidates in offer stage
    cand_rows = await _rows(
        db,
        """
        select id::text as id, full_name, ai_score, created_at
        from public.candidates
        where org_id=:org and status='offer'
        """,
        {"org": org_id},
    )
    for c in cand_rows:
        out.append(Approval(
            id=f"offer-{c['id']}",
            kind="offer",
            title=f"Offer · {c['full_name']}",
            detail=f"AI score {c['ai_score'] or '—'}. Confirm offer letter & comp.",
            requires_role="hr",
            severity="urgent",
            created_at=str(c.get("created_at") or datetime.now(timezone.utc).isoformat()),
            cta_label="Open candidate",
            cta_href="/app/talent",
            approve_endpoint=f"/recruiting/candidates/{c['id']}/decision?hire=true",
            deny_endpoint=f"/recruiting/candidates/{c['id']}/decision?hire=false",
        ))

    # 4. Agent actions requiring approval
    runs = list_runs(org_id)
    for r in runs:
        for a in r.actions:
            if not a.approval_required:
                continue
            out.append(Approval(
                id=f"agent-{r.id}-{a.id}",
                kind="agent_action",
                title=a.title,
                detail=a.rationale or f"{r.agent.replace('_', ' ')} agent",
                requires_role="hr",
                severity="normal",
                created_at=r.started_at,
                cta_label="Open agent",
                cta_href=f"/app/agents?agent={r.agent}",
                approve_endpoint=f"/agents/{r.agent}/approve-action/{a.id}",
            ))

    # 5. COMP LETTERS ARE NOT WIRED YET, and this queue no longer pretends
    # otherwise.
    #
    # Two invented approvals used to be appended here — "Comp letter · Sam
    # Rivera" and "Promotion · Avery Chen — Engineering Lead, Payments, 89%
    # role-fit per marketplace" — under a comment that admitted they were
    # synthetic. They rendered beside genuine items (offers pulled from
    # candidates, agent actions awaiting approval) with nothing to tell them
    # apart, in a queue whose entire purpose is that someone acts on it. Their
    # CTA opened a comp review for a person who does not exist, and the 89%
    # role-fit came from no marketplace.
    #
    # An approvals inbox with two fewer rows is worth more than one a user
    # learns to distrust. The gap is reported instead.
    pending_feature = [{
        "topic": "Comp letters and promotions",
        "reason": "there is no comp_letters table, so nothing can be queued for "
                  "approval here yet.",
        "needs": "comp letter records with an approver and a decision.",
    }]

    if kind:
        out = [a for a in out if a.kind == kind]

    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {"urgent": 0, "normal": 0, "low": 0}
    for a in out:
        by_kind[a.kind] = by_kind.get(a.kind, 0) + 1
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1

    return {
        "items": [a.to_dict() for a in out],
        "counts": {
            "total": len(out),
            "by_kind": by_kind,
            "by_severity": by_severity,
        },
        "unavailable": pending_feature,
    }


def _within_days(date_obj, days: int) -> bool:
    if not date_obj:
        return False
    try:
        if isinstance(date_obj, str):
            d = datetime.fromisoformat(date_obj).replace(tzinfo=timezone.utc)
        elif hasattr(date_obj, "isoformat"):
            d = datetime.fromisoformat(date_obj.isoformat())
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
        else:
            return False
        return (d - datetime.now(timezone.utc)).days <= days
    except Exception:
        return False
