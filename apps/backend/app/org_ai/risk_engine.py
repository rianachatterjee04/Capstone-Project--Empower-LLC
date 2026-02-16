from .workforce_graph import compute_relationship_risk

def compute_risk(context):

    risk = {}

    # performance drop detection
    if context.performance:
        score = context.performance.get("score", 3)
        risk["performance_risk"] = max(0, (3 - score) / 3)

    # compensation risk
    if context.employee:
        salary = context.employee.get("salary", 0)
        if salary < 80000:
            risk["attrition_risk"] = 0.6

    # manager toxicity
    risk["manager_risk"] = compute_relationship_risk(context)

    return risk

