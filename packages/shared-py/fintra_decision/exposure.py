"""Multi-dimensional Consequence & Exposure — separate dimensions + escalation.

"Blast radius" is too cybersecurity-shaped. A high-consequence action has several
independent exposure dimensions — financial, customer, employee, security,
operational, compliance, safety, reversibility — and an action can be *technically
authorized* yet carry $2M of exposure across 15,000 customers and be irreversible,
which should require additional approval.

This module:
  * `assess_exposure(...)` — build an `Exposure` from explicit per-dimension inputs,
    defaulting every un-supplied dimension to **UNKNOWN** (never fabricated).
  * `exposure_escalation(exposure, thresholds)` — the verdict floor imposed purely by
    exposure magnitude / irreversibility, independent of invariants. This is what
    lets the engine say "authorized, but escalate to CFO + Security".

Pure + dependency-free. UNKNOWN is honest (do not invent precision).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .contract import Exposure, Verdict, SEVERITY

_QUAL = {"none", "low", "medium", "high", "unknown"}


def assess_exposure(*, financial: Optional[float] = None,
                    customers: Optional[int] = None, employees: Optional[int] = None,
                    security: str = "unknown", operational: str = "unknown",
                    compliance: str = "unknown", safety: str = "unknown",
                    reputational: str = "unknown", reversibility: str = "unknown") -> Exposure:
    """Every dimension is explicit or UNKNOWN — no dimension is inferred to zero."""
    def q(v: str) -> str:
        return v if v in _QUAL else "unknown"
    return Exposure(financial=financial, customers_affected=customers, employees_affected=employees,
                    security=q(security), operational=q(operational), compliance=q(compliance),
                    safety=q(safety), reputational=q(reputational), reversibility=reversibility)


def exposure_escalation(exposure: Exposure, *,
                        financial_step: float = 50_000, financial_hold: float = 250_000,
                        customers_hold: int = 10_000, employees_hold: int = 500
                        ) -> Tuple[Verdict, List[str]]:
    """The verdict FLOOR from exposure alone (ignoring invariants):
      * irreversible / high safety or compliance / big $ / many customers|employees → HOLD
      * mid-band financial → STEP_UP
      * otherwise → ALLOW (no exposure-driven escalation)
    Returns (floor, reasons). UNKNOWN dimensions never escalate (honest)."""
    floor = Verdict.ALLOW
    reasons: List[str] = []

    def raise_to(v: Verdict, why: str) -> None:
        nonlocal floor
        if SEVERITY[v] > SEVERITY[floor]:
            floor = v
        reasons.append(why)

    fin = exposure.financial
    if fin is not None and fin >= financial_hold:
        raise_to(Verdict.HOLD, f"${fin:,.0f} financial exposure ≥ ${financial_hold:,.0f}")
    elif fin is not None and fin >= financial_step:
        raise_to(Verdict.STEP_UP, f"${fin:,.0f} financial exposure ≥ ${financial_step:,.0f}")

    if exposure.customers_affected and exposure.customers_affected >= customers_hold:
        raise_to(Verdict.HOLD, f"{exposure.customers_affected:,} customers affected")
    if exposure.employees_affected and exposure.employees_affected >= employees_hold:
        raise_to(Verdict.HOLD, f"{exposure.employees_affected:,} employees affected")

    rev = (exposure.reversibility or "").lower()
    if rev.startswith("irrevers"):
        raise_to(Verdict.HOLD, "action is irreversible")

    if exposure.safety == "high":
        raise_to(Verdict.HOLD, "high safety exposure")
    if exposure.compliance == "high":
        raise_to(Verdict.HOLD, "high compliance exposure")
    if exposure.security == "high":
        raise_to(Verdict.STEP_UP, "high security exposure")

    return floor, reasons
