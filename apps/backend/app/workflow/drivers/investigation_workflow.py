from __future__ import annotations
from typing import Any, Dict

from app.realtime.bus import publish
from app.realtime.decision import request_decision


async def handle_case_event(
    db,
    event: str,
    payload: Dict[str, Any],
    action: str | None
):
    """
    Harassment / ethics complaint behavioral workflow

    This driver controls:
    - automatic escalation
    - ombudsman routing
    - legal escalation
    - retaliation monitoring
    - human decision interrupts
    - UI realtime updates
    """

    case_id = payload.get("case_id")
    severity = payload.get("severity")
    category = payload.get("category")
    anonymous = payload.get("anonymous", False)

    # =====================================================
    # CASE CREATED
    # =====================================================
    if event == "case.created":

        # -------------------------
        # CRITICAL → HUMAN DECISION
        # -------------------------
        if severity == "critical":

            await request_decision(
                title="Critical Workplace Complaint",
                message="A high-risk complaint was filed. Choose handling strategy.",
                context={
                    "case_id": case_id,
                    "severity": severity,
                    "category": category
                },
                actions=[
                    {"id": "legal", "label": "Escalate to Legal", "style": "danger"},
                    {"id": "hr", "label": "Assign HR Leadership", "style": "primary"},
                    {"id": "ombudsman", "label": "Ombudsman Review", "style": "secondary"},
                    {"id": "monitor", "label": "Monitor Only", "style": "ghost"}
                ]
            )

            return {"awaiting_human": True}

        # -------------------------
        # HIGH → AUTO LEGAL
        # -------------------------
        if severity == "high":
            await publish({
                "type": "case_escalated",
                "case_id": case_id,
                "level": "legal"
            })
            return {"escalated": True, "level": "legal"}

        # -------------------------
        # SENSITIVE CATEGORY → HR
        # -------------------------
        if category in ("harassment", "discrimination", "retaliation"):
            await publish({
                "type": "case_escalated",
                "case_id": case_id,
                "level": "hr_leadership"
            })
            return {"escalated": True, "level": "hr"}

        # -------------------------
        # ANONYMOUS → OMBUDSMAN
        # -------------------------
        if anonymous:
            await publish({
                "type": "case_ombudsman_queue",
                "case_id": case_id
            })
            return {"queued": "ombudsman"}

        # -------------------------
        # NORMAL
        # -------------------------
        await publish({
            "type": "case_received",
            "case_id": case_id
        })
        return {"queued": True}

    # =====================================================
    # HUMAN DECISION RESULT
    # =====================================================
    if event == "decision.made":

        decision = payload.get("action")

        if decision == "legal":
            await publish({
                "type": "case_escalated",
                "case_id": case_id,
                "level": "legal"
            })
            return {"decision_executed": "legal"}

        if decision == "hr":
            await publish({
                "type": "case_escalated",
                "case_id": case_id,
                "level": "hr_leadership"
            })
            return {"decision_executed": "hr"}

        if decision == "ombudsman":
            await publish({
                "type": "case_ombudsman_queue",
                "case_id": case_id
            })
            return {"decision_executed": "ombudsman"}

        if decision == "monitor":
            await publish({
                "type": "case_monitoring",
                "case_id": case_id
            })
            return {"decision_executed": "monitor"}

    # =====================================================
    # CASE ASSIGNED
    # =====================================================
    if event == "case.assigned":
        await publish({
            "type": "case_assigned",
            "case_id": case_id
        })
        return {"assigned": True}

    # =====================================================
    # EVIDENCE ADDED
    # =====================================================
    if event == "case.evidence_added":
        await publish({
            "type": "case_updated",
            "case_id": case_id
        })
        return {"updated": True}

    # =====================================================
    # FINDINGS RECORDED
    # =====================================================
    if event == "case.findings_recorded":
        await publish({
            "type": "case_ready_for_decision",
            "case_id": case_id
        })
        return {"ready_for_action": True}

    # =====================================================
    # DISCIPLINARY ACTION
    # =====================================================
    if event == "case.action_taken":
        await publish({
            "type": "case_action_logged",
            "case_id": case_id
        })
        return {"action_logged": True}

    # =====================================================
    # CASE CLOSED
    # =====================================================
    if event == "case.closed":
        await publish({
            "type": "case_closed",
            "case_id": case_id
        })
        return {"closed": True}

    return {"ignored": event}

