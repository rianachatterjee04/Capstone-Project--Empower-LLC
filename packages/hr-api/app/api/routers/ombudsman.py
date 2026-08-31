"""Ombudsman / Employee Relations router.

Sits above the core /cases CRUD endpoints and adds:
- AI-assisted triage (category + severity suggestion + risk summary)
- Confidentiality-first list view that strips identifying details for non-HR roles
- Quick "risk dashboard" aggregation across open cases

Read access is restricted: only HR/legal/admin/owner can list non-anonymized case
detail. Reporters can always see their own case status. Managers are explicitly
excluded by default to avoid retaliation risk.
"""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent, Case


router = APIRouter(prefix="/ombudsman", tags=["ombudsman"])


PRIVILEGED_ROLES = {"owner", "admin", "hr", "legal"}


# ---------------------------------------------------------------------------
# AI triage — heuristic categorization + severity suggestion.
# Keeps it explainable. Real systems can swap in an LLM call here.
# ---------------------------------------------------------------------------
CATEGORY_RULES: dict[str, list[str]] = {
    "harassment": ["harass", "unwanted advance", "bullying", "intimidat", "threat"],
    "discrimination": ["discriminat", "race", "gender", "age ", "religion", "disability", "lgbt"],
    "retaliation": ["retaliat", "punish", "reprisal"],
    "safety": ["unsafe", "injury", "accident", "fire", "hazard"],
    "payroll": ["paycheck", "payroll", "overtime not paid", "missing pay", "underpaid"],
    "ethics": ["fraud", "bribe", "kickback", "conflict of interest", "embezzle"],
    "policy_violation": ["policy", "violation", "breach"],
}

SEVERITY_HIGH = ["threat", "weapon", "assault", "injury", "harass", "retaliat", "fraud", "child", "minor", "illegal"]


def _suggest_category(details: str) -> str:
    text = (details or "").lower()
    best_cat = "general"
    best_hits = 0
    for cat, kws in CATEGORY_RULES.items():
        hits = sum(1 for kw in kws if kw in text)
        if hits > best_hits:
            best_hits = hits
            best_cat = cat
    return best_cat


def _suggest_severity(details: str, current: str | None = None) -> str:
    t = (details or "").lower()
    if any(k in t for k in SEVERITY_HIGH):
        return "high"
    if current == "high":
        return "high"
    return "medium" if len(t) > 200 else "low"


def _redact(text: str) -> str:
    """Crude PII redaction for surfaces visible to non-privileged roles."""
    if not text:
        return ""
    text = re.sub(r"\b[\w.-]+@[\w.-]+\.\w+\b", "[email]", text)
    text = re.sub(r"\b\+?\d[\d\s().-]{7,}\d\b", "[phone]", text)
    return text


def _summarize(details: str) -> str:
    txt = (details or "").strip()
    if not txt:
        return ""
    txt = re.sub(r"\s+", " ", txt)
    return txt[:280] + ("…" if len(txt) > 280 else "")


# ---------------------------------------------------------------------------
@router.post("/triage")
async def triage(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Run AI triage on raw report text WITHOUT persisting the case yet.

    The reporter UI can call this to show a preview/category before final submit.
    """
    details = (payload.get("details") or "").strip()
    if not details:
        raise HTTPException(status_code=400, detail="details required")

    suggested_category = _suggest_category(details)
    suggested_severity = _suggest_severity(details)
    summary = _summarize(details)

    return {
        "summary": summary,
        "suggested_category": suggested_category,
        "suggested_severity": suggested_severity,
        "confidentiality_reminder": (
            "Your report is confidential. Foundry prohibits retaliation against any "
            "good-faith reporter. HR and/or legal will review every submission."
        ),
        "ai_disclaimer": (
            "AI categorization is a starting point. HR will assess the actual category "
            "and severity. You can mark this report anonymous on submit."
        ),
    }


@router.get("")
async def list_cases_ombudsman(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """List cases with confidentiality enforced.

    - Privileged roles see full detail.
    - Others (manager/employee) see only their own reported cases.
    """
    org_id = UUID(actor.org_id)

    if actor.role in PRIVILEGED_ROLES:
        rows = (await db.execute(
            select(Case).where(Case.org_id == org_id).order_by(Case.created_at.desc())
        )).scalars().all()
        return {
            "role_view": "privileged",
            "items": [
                {
                    "id": str(c.id),
                    "category": c.category,
                    "severity": c.severity,
                    "is_anonymous": c.is_anonymous,
                    "status": c.status,
                    "escalation_level": c.escalation_level,
                    "summary": _summarize(c.details),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in rows
            ],
        }

    # Non-privileged: only show their own reports
    try:
        reporter_uuid = UUID(actor.user_id)
    except Exception:
        reporter_uuid = None
    rows = []
    if reporter_uuid is not None:
        rows = (
            await db.execute(
                text(
                    """
                    select c.id, c.category, c.severity, c.status, c.created_at, c.is_anonymous
                    from public.cases c
                    left join public.employees e on e.id = c.reporter_employee_id
                    where c.org_id = :org and e.user_id = :uid
                    order by c.created_at desc
                    """
                ),
                {"org": actor.org_id, "uid": actor.user_id},
            )
        ).mappings().all()
    return {
        "role_view": "reporter",
        "items": [
            {
                "id": str(r["id"]),
                "category": r["category"],
                "severity": r["severity"],
                "status": r["status"],
                "is_anonymous": r["is_anonymous"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
        "note": "You only see cases you submitted. Managers do not have direct access.",
    }


@router.get("/risk-dashboard")
async def risk_dashboard(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    org_id = UUID(actor.org_id)
    rows = (await db.execute(
        select(Case).where(Case.org_id == org_id)
    )).scalars().all()

    by_cat: dict[str, int] = {}
    by_sev: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    by_status: dict[str, int] = {}
    open_high: list[dict] = []
    for c in rows:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
        by_sev[c.severity] = by_sev.get(c.severity, 0) + 1
        by_status[c.status] = by_status.get(c.status, 0) + 1
        if c.severity == "high" and c.status not in ("closed",):
            open_high.append({
                "id": str(c.id),
                "category": c.category,
                "summary": _summarize(c.details),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })

    return {
        "totals": {"all_cases": len(rows)},
        "by_category": by_cat,
        "by_severity": by_sev,
        "by_status": by_status,
        "open_high_severity": open_high,
        "retaliation_reminder": "Foundry prohibits retaliation against good-faith reporters.",
    }


@router.post("/{case_id}/ai-summary")
async def ai_summary(
    case_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Generate an AI summary for a case file. Privileged roles only."""
    if actor.role not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        case_uuid = UUID(case_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid case_id")

    org_id = UUID(actor.org_id)
    c = await db.get(Case, case_uuid)
    if not c or c.org_id != org_id:
        raise HTTPException(status_code=404, detail="Case not found")

    suggested_category = _suggest_category(c.details)
    suggested_severity = _suggest_severity(c.details, current=c.severity)

    summary = {
        "case_id": case_id,
        "category": c.category,
        "severity": c.severity,
        "ai_suggested_category": suggested_category,
        "ai_suggested_severity": suggested_severity,
        "summary": _summarize(c.details),
        "next_steps": [
            "Acknowledge receipt to reporter within 1 business day.",
            "If severity is high, route to legal and pause any related employment actions.",
            "Conduct fact-finding interviews; document each contact.",
            "Maintain confidentiality on a need-to-know basis.",
            "Provide closure update to the reporter when investigation concludes.",
        ],
        "fairness_note": (
            "AI categorisation is a starting point only. Confirm category and severity "
            "with HR/legal. Do not share this summary outside the case team."
        ),
    }

    try:
        db.add(AuditEvent(
            org_id=org_id,
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ombudsman.ai_summary",
            entity_type="case",
            entity_id=case_uuid,
            payload={
                "suggested_category": suggested_category,
                "suggested_severity": suggested_severity,
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return summary
