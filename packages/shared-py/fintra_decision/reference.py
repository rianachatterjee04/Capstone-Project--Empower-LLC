"""Reference engines — two domains, one contract, to prove the seam is real.

These are intentionally small and pure. In production each is a thin ADAPTER over
an existing engine that already ships:

  * FinanceDecisionEngine  -> packages/api evaluate_payment / internal_finance
                              (its `recommended_action` maps through normalize_verdict)
  * SecurityDecisionEngine -> packages/aegis action PDP (/pdp/decide)
                              (its `verdict` maps through normalize_verdict)

The adapter's only job is to translate the engine's native output into a
canonical, sealed DecisionResponse. Everything downstream — trust ledger,
Verified-Autonomy console, assurance receipts — consumes that one shape.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .contract import (
    DecisionRequest,
    DecisionResponse,
    Verdict,
    band_from_score,
    normalize_verdict,
)

FINANCE_ACTIONS = {
    "pay_invoice", "issue_refund", "run_payroll", "onboard_vendor",
    "change_vendor_bank", "post_journal", "send_wire",
}
SECURITY_ACTIONS = {
    "delete_iam_policy", "change_iam", "deploy", "merge_pr",
    "rotate_secret", "open_network", "disable_mfa",
}


def _tone(score: float) -> str:
    if score >= 0.7:
        return "danger"
    if score >= 0.4:
        return "warn"
    return "neutral"


class FinanceDecisionEngine:
    """Reference finance engine. Prefers the native `recommended_action` on the
    request envelope (as evaluate_payment / internal_finance would emit), and only
    falls back to a trivial amount rule when no envelope is present."""

    domain = "finance"

    def handles(self, request: DecisionRequest) -> bool:
        return request.context.domain == "finance" or request.action.type in FINANCE_ACTIONS

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        env = request.context.envelope or {}
        native = env.get("recommended_action")
        verdict = normalize_verdict(native) if native else _finance_fallback(request)

        risk = int(env["risk"]) if "risk" in env else _finance_risk(request)
        score = max(0, 100 - risk)

        drivers: List[Dict[str, Any]] = [
            {
                "label": s.get("type", "signal"),
                "weight": int(round(float(s.get("score", 0)) * 100)),
                "tone": _tone(float(s.get("score", 0))),
            }
            for s in request.context.signals
        ]

        approvals: List[str] = []
        comp: List[str] = []
        if verdict == Verdict.STEP_UP:
            approvals = ["second_approver"]
        elif verdict == Verdict.HOLD:
            approvals = ["controller"]
            comp = ["hold_payment"]
        elif verdict == Verdict.BLOCK:
            comp = ["hold_payment", "reverse_journal"]

        return DecisionResponse(
            request_id=request.request_id,
            domain="finance",
            engine="finance.reference",
            verdict=verdict,
            trust_score=score,
            band=band_from_score(score),
            drivers=drivers,
            required_approvals=approvals,
            compensating_actions=comp,
            explanation=str(env.get("explanation", "")),
        ).sealed()


def _finance_risk(request: DecisionRequest) -> int:
    amount = request.context.amount or 0
    if amount >= 50_000:
        return 60
    if amount >= 10_000:
        return 30
    return 10


def _finance_fallback(request: DecisionRequest) -> Verdict:
    amount = request.context.amount or 0
    if amount >= 50_000:
        return Verdict.HOLD
    if amount >= 10_000:
        return Verdict.STEP_UP
    return Verdict.ALLOW


class SecurityDecisionEngine:
    """Reference security engine mirroring the Aegis PDP's risk posture: privilege,
    production blast radius, and irreversibility drive the verdict."""

    domain = "security"

    def handles(self, request: DecisionRequest) -> bool:
        return request.context.domain == "security" or request.action.type in SECURITY_ACTIONS

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        risk = 15
        drivers: List[Dict[str, Any]] = []

        if request.target.environment == "prod":
            risk += 30
            drivers.append({"label": "production target", "weight": 30, "tone": "danger"})
        if request.actor.privileged:
            risk += 20
            drivers.append({"label": "privileged actor", "weight": 20, "tone": "warn"})
        if not request.action.reversible:
            risk += 25
            drivers.append({"label": "irreversible action", "weight": 25, "tone": "danger"})
        if request.target.blast_radius == "enterprise":
            risk += 20
            drivers.append({"label": "enterprise blast radius", "weight": 20, "tone": "danger"})
        if request.actor.identity_confidence < 0.6:
            risk += 15
            drivers.append({"label": "weak identity confidence", "weight": 15, "tone": "warn"})

        risk = min(risk, 99)
        score = max(0, 100 - risk)

        if risk >= 80:
            verdict = Verdict.BLOCK
        elif risk >= 60:
            verdict = Verdict.HOLD
        elif risk >= 40:
            verdict = Verdict.STEP_UP
        else:
            verdict = Verdict.ALLOW

        approvals: List[str] = []
        comp: List[str] = []
        if verdict == Verdict.STEP_UP:
            approvals = ["second_approver"]
        elif verdict in (Verdict.HOLD, Verdict.BLOCK):
            approvals = ["security_owner"]
            comp = ["restore_previous_state", "revoke_session"]

        return DecisionResponse(
            request_id=request.request_id,
            domain="security",
            engine="security.reference",
            verdict=verdict,
            trust_score=score,
            band=band_from_score(score),
            drivers=drivers,
            required_approvals=approvals,
            compensating_actions=comp,
            explanation=f"{request.action.type} on {request.target.environment} target",
        ).sealed()


def default_registry():
    """A registry wired with the two reference engines. Register real adapters in
    the same way at the service boundary."""
    from .engine import DecisionRegistry

    registry = DecisionRegistry()
    registry.register(FinanceDecisionEngine())
    registry.register(SecurityDecisionEngine())
    return registry
