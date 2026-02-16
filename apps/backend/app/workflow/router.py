from __future__ import annotations

from app.workflow.drivers.hiring_workflow import handle_hiring_event
from app.workflow.drivers.investigation_workflow import handle_case_event
from app.workflow.drivers.comp_cycle_engine import handle_comp_event
from app.workflow.drivers.onboarding_enforcement import check_onboarding
from app.realtime.bus import publish


# =========================================================
# Central Action Router
# =========================================================
async def route_action(db, event: str, payload: dict, decision: dict):
    """
    Executes the behavior chosen by OrgAI.

    Flow:
        engine.trigger()
            → org_ai decides action
            → router executes domain logic
            → realtime publishes result
    """

    action = decision.get("action")
    result = {"event": event, "action": action}

    # =====================================================
    # HUMAN DECISION EVENTS (must run first)
    # =====================================================
    if event == "decision.made":
        result["result"] = await handle_case_event(db, event, payload, action)
        await publish(event, result)
        return result

    # =====================================================
    # Hiring domain
    # =====================================================
    if event.startswith("candidate."):
        result["result"] = await handle_hiring_event(db, event, payload, action)

    # =====================================================
    # Cases / investigations
    # =====================================================
    elif event.startswith("case."):
        result["result"] = await handle_case_event(db, event, payload, action)

    # =====================================================
    # Compensation
    # =====================================================
    elif event.startswith("comp."):
        result["result"] = await handle_comp_event(db, event, payload, action)

    # =====================================================
    # Onboarding
    # =====================================================
    elif event.startswith("employee.onboarding"):
        result["result"] = await check_onboarding(db, payload, action)

    # =====================================================
    # Unknown
    # =====================================================
    else:
        result["result"] = {"ignored": event}

    # =====================================================
    # 🔥 REALTIME BROADCAST (CRITICAL)
    # =====================================================
    await publish(event, result)

    return result

