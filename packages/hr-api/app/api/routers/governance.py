"""HR governance seam for Trust CORTEX (cross-domain trust synthesis).

Exposes the HR module's PENDING GOVERNANCE DECISIONS — the workforce decisions
awaiting a human sign-off — normalized to the ONE cross-domain contract Fintra's
Trust CORTEX consumes, so an HR bank-account change or a high-attrition backfill
can be ranked on the SAME scale as a finance bill-pay or a compliance control gap.

    GET /governance/pending-decisions

Every row is a REAL, existing HR surface (nothing invented):
  * pending amount-tier approvals  (public.approval_requests — real DB rows:
    payroll / comp / offer / bank-account changes awaiting sign-off)
  * the Workforce Risk engine's live alerts (app.services.workforce_risk_service.scan
    — attrition, comp-equity, burnout, open high-severity cases, thin hiring),
    each of which is a decision leadership must act on.

Contract per decision (what CORTEX's engine.normalize_external_decision expects):
    {id, title, actor, counterparty, exposure_usd | impact(0..1), urgency(0..1),
     urgency_label, trust_score(0..100), recommended_verdict, deep_link, reason,
     kind, trust_context, guardrail_action}

Fail-soft end-to-end: a source whose tables aren't provisioned contributes an
empty list, never a 500 — mirrors the rest of hr-api.

AUTH: require_org (Bearer / dev: token). The token's org scopes the data, so
CORTEX simply forwards a configured bearer — no new auth path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org

router = APIRouter(prefix="/governance", tags=["governance"])


# severity → the CORTEX inputs. Lower trust + higher impact/urgency = riskier.
_SEV = {
    "critical": {"impact": 0.95, "urgency": 0.8, "trust": 38.0},
    "high":     {"impact": 0.85, "urgency": 0.7, "trust": 45.0},
    "medium":   {"impact": 0.5,  "urgency": 0.45, "trust": 60.0},
    "low":      {"impact": 0.25, "urgency": 0.25, "trust": 70.0},
}

# HR approval type → a human-facing kind + the deep link into the HR app.
_APPROVAL_KIND = {
    "payroll": ("Payroll change", "/approvals"),
    "bank_account": ("Bank-account change", "/approvals"),
    "bank": ("Bank-account change", "/approvals"),
    "comp": ("Compensation change", "/comp"),
    "compensation": ("Compensation change", "/comp"),
    "equity": ("Equity grant", "/equity"),
    "offer": ("Offer sign-off", "/recruiting"),
    "termination": ("Termination sign-off", "/approvals"),
}

# Riskier approval types get docked more trust — a payroll/bank-account change is
# the classic fraud vector, so it fails toward challenge even at a modest amount.
_APPROVAL_TRUST_PENALTY = {
    "bank_account": 30.0, "bank": 30.0, "payroll": 22.0,
    "comp": 12.0, "compensation": 12.0, "equity": 14.0,
    "offer": 8.0, "termination": 18.0,
}

_BASE_TRUST = 75.0


def _verdict(trust: float, *, impact: float = 0.0) -> str:
    if trust < 25:
        return "block"
    if trust < 55 or impact >= 0.85:
        return "challenge"
    return "approve"


def _kind_deep_link(kind: str) -> str:
    return {
        "attrition": "/workforce/risk",
        "comp_equity": "/comp",
        "burnout": "/workforce/risk",
        "compliance": "/investigations",
        "manager": "/workforce/risk",
        "hiring": "/recruiting",
    }.get(kind, "/workforce/risk")


async def _approval_decisions(db: AsyncSession, org_id: str) -> List[Dict[str, Any]]:
    """Real pending amount-tier approvals (payroll/comp/offer/bank-account)."""
    try:
        rows = (await db.execute(text("""
            select id, title, type, amount, requested_by, created_at
            from public.approval_requests
            where org_id = :org_id and status = 'pending'
            order by amount desc nulls last, created_at asc
            limit 50
        """), {"org_id": org_id})).mappings().all()
    except Exception:
        await db.rollback()
        return []

    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for r in rows:
        atype = str(r.get("type") or "").lower()
        kind, deep = _APPROVAL_KIND.get(atype, ("HR approval", "/approvals"))
        amount = r.get("amount")
        penalty = _APPROVAL_TRUST_PENALTY.get(atype, 6.0)

        # aging → urgency
        created = r.get("created_at")
        age_days = 0
        try:
            if created is not None:
                c = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
                age_days = max((now - c).days, 0)
        except Exception:
            age_days = 0
        if age_days >= 3:
            urgency, ulabel = 0.7, f"{age_days}d awaiting sign-off"
        elif age_days >= 1:
            urgency, ulabel = 0.5, f"{age_days}d awaiting sign-off"
        else:
            urgency, ulabel = 0.4, "awaiting sign-off"

        trust = max(_BASE_TRUST - penalty - min(age_days * 2.0, 15.0), 0.0)
        verdict = _verdict(trust)
        out.append({
            "id": f"approval:{r.get('id')}",
            "kind": kind,
            "title": str(r.get("title") or f"{kind} approval"),
            "actor": str(r.get("requested_by") or "HR requester"),
            "counterparty": kind,
            "exposure_usd": float(amount) if amount is not None else None,
            "urgency": urgency,
            "urgency_label": ulabel,
            "trust_score": round(trust, 1),
            "recommended_verdict": verdict,
            "deep_link": deep,
            "reason": (f"{kind} awaiting sign-off"
                       + (f" — ${float(amount):,.0f} exposure." if amount is not None else ".")),
            "trust_context": (f"{kind} is a high-trust-sensitivity change"
                              if penalty >= 20 else f"{kind} pending in the approvals inbox"),
            "guardrail_action": ("Require dual sign-off + verify the change out-of-band before releasing"
                                 if verdict != "approve" else "Clear to approve on standard controls"),
        })
    return out


async def _workforce_risk_decisions(db: AsyncSession, org_id: str) -> List[Dict[str, Any]]:
    """The Workforce Risk engine's live alerts as governance decisions."""
    try:
        from app.services.workforce_risk_service import scan
        summary = await scan(db, org_id)
        alerts = summary.to_dict().get("alerts", [])
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for a in alerts:
        sev = str(a.get("severity") or "medium").lower()
        p = _SEV.get(sev, _SEV["medium"])
        kind = str(a.get("kind") or "workforce")
        subject = str(a.get("subject") or "workforce")
        drivers = a.get("drivers") or []
        action = str(a.get("recommended_action") or "Review with HR")
        trust = p["trust"]
        verdict = _verdict(trust, impact=p["impact"])
        # A DECISION QUEUE IS FOR THINGS SOMEBODY MUST SIGN OFF.
        #
        # These come straight from the workforce risk engine, whose four
        # people-layers run on a sample cohort. Four of the five decisions in
        # this queue were "Attrition risk — Avery Chen", "Burnout risk — Avery
        # Chen", "Comp Equity risk — Avery Chen", "Manager risk — Morgan Lee",
        # ranked on a trust scale and presented as awaiting sign-off, for an
        # organisation where none of those people work.
        #
        # The alerts now carry their source; this passes it through rather than
        # dropping it on the way into the queue.
        is_sample = a.get("source", "employee_record") != "employee_record"
        out.append({
            "id": f"wfrisk:{a.get('id')}",
            "kind": f"Workforce {kind.replace('_', ' ')}",
            "title": (f"{kind.replace('_', ' ').title()} risk — {subject}"
                      + (" (sample)" if is_sample else "")),
            "is_sample": is_sample,
            "actor": "Workforce Risk engine",
            "counterparty": subject,
            # no defensible dollar figure → carry qualitative impact, not an invented $.
            "impact": p["impact"],
            "urgency": p["urgency"],
            "urgency_label": f"{sev} severity",
            "trust_score": trust,
            "recommended_verdict": verdict,
            "deep_link": _kind_deep_link(kind),
            "reason": action,
            "trust_context": "; ".join(str(d) for d in drivers) or "Workforce risk signal above threshold",
            "guardrail_action": action,
        })
    return out


@router.get("/pending-decisions")
async def pending_decisions(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
) -> Dict[str, Any]:
    """HR pending governance decisions, normalized to the CORTEX contract."""
    decisions: List[Dict[str, Any]] = []
    decisions.extend(await _approval_decisions(db, actor.org_id))
    decisions.extend(await _workforce_risk_decisions(db, actor.org_id))
    for d in decisions:
        d["module"] = "hr"
    return {"module": "hr", "org_id": actor.org_id,
            "count": len(decisions), "decisions": decisions}
