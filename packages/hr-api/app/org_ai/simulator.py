from __future__ import annotations
from statistics import mean

from .org_graph import OrgGraph


# ============================================================
# STRUCTURAL SIMULATION (organizational physics)
# ============================================================

def structural_simulation(context):
    """
    Management science layer:
    evaluates org structure health
    """

    graph = OrgGraph(context.employees or [])
    event = context.event
    payload = context.payload

    if event == "performance.review.finalized":
        emp_id = payload.get("employee_id")
        if not emp_id:
            return {}

        team = graph.team_size(emp_id)
        pay_stats = graph.pay_distribution()

        span_risk = team > 12
        comp_risk = (pay_stats["max"] - pay_stats["min"]) > pay_stats["avg"]

        return {
            "span_of_control_risk": span_risk,
            "pay_compression_risk": comp_risk,
            "structural_risk_score": int(span_risk) + int(comp_risk)
        }

    if event == "termination.requested":
        emp_id = payload.get("employee_id")
        team = graph.team_size(emp_id)
        return {"knowledge_loss": "high" if team > 5 else "low"}

    return {}


# ============================================================
# BEHAVIORAL SIMULATION (human reactions)
# ============================================================

def behavioral_simulation(context, structural):
    """
    Predict how humans react to decisions
    """

    event = context.event

    # --------------------------------------------------
    # Promotion psychology
    # --------------------------------------------------
    if event == "performance.review.finalized" and context.employee:

        peer_levels = [e.get("level") for e in context.team or [] if e.get("level")]
        peer_avg = mean(peer_levels) if peer_levels else context.employee.get("level", 1)

        leapfrog = context.employee.get("level", 1) > peer_avg + 2

        promotion_risk = 0.8 if leapfrog else 0.2
        if structural.get("span_of_control_risk"):
            promotion_risk += 0.15

        return {
            "promotion_success_probability": max(0, 1 - promotion_risk),
            "attrition_risk_if_denied": 0.65 if context.employee.get("level",1) >= peer_avg else 0.25
        }

    # --------------------------------------------------
    # Hiring load psychology
    # --------------------------------------------------
    if event == "candidate.hired":
        headcount = len(context.employees or [])
        return {
            "manager_load_increase": 1 / max(headcount,1),
            "onboarding_overload": headcount > 50
        }

    # --------------------------------------------------
    # Legal liability psychology
    # --------------------------------------------------
    if event == "case.created":
        severity_map = {"low":0.1,"medium":0.4,"high":0.7,"critical":0.95}
        severity = next((c["severity"] for c in context.cases if c["id"] == context.payload.get("case_id")), "low")
        return {"legal_liability": severity_map.get(severity,0.2)}

    return {}


# ============================================================
# MASTER SIMULATION
# ============================================================

def simulate_outcomes(context):
    """
    Unified simulation pipeline.
    This feeds the decision engine.
    """

    structural = structural_simulation(context)
    behavioral = behavioral_simulation(context, structural)

    return {
        "structural": structural,
        "behavioral": behavioral
    }

