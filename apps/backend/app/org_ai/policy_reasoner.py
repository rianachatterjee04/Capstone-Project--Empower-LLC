def apply_company_policy(event, context, risk):

    if event == "case.created":
        if risk.get("manager_risk", 0) > 0.5:
            return "legal_escalation"

    if event == "performance.review.finalized":
        if risk.get("performance_risk", 0) > 0.7:
            return "start_pip"

    return None

