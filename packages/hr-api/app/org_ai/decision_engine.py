from __future__ import annotations

from .types import OrgDecision, OrgContext
from .risk_engine import compute_risk
from .policy_reasoner import apply_company_policy
from .simulator import simulate_outcomes
from .strategy import choose_strategy


async def decide(context: OrgContext) -> OrgDecision:
    """
    Central reasoning pipeline.
    This is the actual OrgAI brain.
    """

    # --------------------------------------------------
    # 1️⃣ Risk Analysis
    # --------------------------------------------------
    risk = compute_risk(context)

    # --------------------------------------------------
    # 2️⃣ Company Policy Enforcement
    # --------------------------------------------------
    policy_action = apply_company_policy(context.event, context, risk)

    # hard legal override
    if policy_action:
        return OrgDecision(
            action=policy_action,
            confidence=0.97,
            reasoning="Company policy enforcement",
            metadata={"risk": risk}
        )

    # --------------------------------------------------
    # 3️⃣ Predict Future Outcomes
    # --------------------------------------------------
    simulations = simulate_outcomes(context)

    # --------------------------------------------------
    # 4️⃣ Strategic Selection
    # --------------------------------------------------
    strategy = choose_strategy(context, simulations, risk)

    # --------------------------------------------------
    # 5️⃣ Final Decision
    # --------------------------------------------------
    return OrgDecision(
        action=strategy["action"],
        confidence=strategy["confidence"],
        reasoning=strategy["reason"],
        metadata={
            "risk": risk,
            "simulations": simulations
        }
    )

