def choose_strategy(context, simulations, risk):
    event = context.event

    # ----------------------------------------
    # HARASSMENT
    # ----------------------------------------
    if event == "case.created":
        liability = simulations.get("legal_liability", 0)

        if liability > 0.8:
            return {"action": "legal_escalation", "confidence":0.95, "reason":"High liability risk"}

        if liability > 0.5:
            return {"action": "hr_investigation_priority", "confidence":0.88, "reason":"Moderate liability"}

        return {"action": "standard_queue", "confidence":0.75, "reason":"Low severity"}

    # ----------------------------------------
    # PROMOTION
    # ----------------------------------------
    if event == "performance.review.finalized":
        success = simulations.get("promotion_success_probability",0.5)
        attrition = simulations.get("attrition_risk_if_denied",0.2)

        if success > 0.7:
            return {"action":"approve_promotion","confidence":0.9,"reason":"High success probability"}

        if attrition > 0.6:
            return {"action":"approve_with_raise","confidence":0.82,"reason":"Retention risk"}

        return {"action":"delay_promotion","confidence":0.78,"reason":"Hierarchy imbalance"}

    # ----------------------------------------
    # ONBOARDING
    # ----------------------------------------
    if event == "employee.onboarding.completed":
        return {"action":"grant_system_access","confidence":0.9,"reason":"Employee active"}

    return {"action":"log_only","confidence":0.5,"reason":"No strategic action"}

