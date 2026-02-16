def attrition_risk(employee: dict) -> float:
    risk = 0.1

    if employee.get("level") in ("junior","entry"):
        risk += 0.2

    if employee.get("salary",0) < 80000:
        risk += 0.25

    return min(risk, 0.9)


def harassment_liability(case: dict) -> float:
    sev = case.get("severity","low")
    return {
        "low": 0.2,
        "medium": 0.5,
        "high": 0.85,
        "critical": 0.95
    }.get(sev, 0.3)

