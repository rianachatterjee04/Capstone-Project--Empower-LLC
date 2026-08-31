"""Supervisor metrics / observability — count what SentriAI supervises.

The universal supervisor should be measurable from day one: how many machine
missions it observed, how many it allowed / held / blocked, how many invariants
were violated, how many post-action verifications FAILED (the action "succeeded"
but the mission did not), how much exposure it flagged, and how much evidence it
sealed. These are both operational metrics and — over time — the proprietary
**Outcome Dataset** moat.

Pure + deterministic: metrics are computed from decision/proof records, not wall
time (no timing metrics here — those need real timestamps supplied by the caller).
Only what is honestly derivable is counted; nothing is estimated as fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# verdicts that need a human before proceeding
_NEEDS_HUMAN = {"step_up", "hold", "block"}
_STOPS = {"hold", "block"}


def _entry(response, proof=None) -> Dict[str, Any]:
    """Normalize a DecisionResponse (+ optional ProofObject) to a flat record."""
    verdict = response.verdict.value if hasattr(response.verdict, "value") else str(response.verdict)
    inv = getattr(response, "invariant_results", []) or []
    exposure = None
    outcome = None
    if proof is not None:
        outcome = (proof.outcome or {}).get("status") if isinstance(proof.outcome, dict) else None
        cons = proof.consequence if isinstance(proof.consequence, dict) else None
        exposure = (cons or {}).get("exposure") if cons else None
    return {"verdict": verdict, "domain": getattr(response, "domain", ""),
            "engine": getattr(response, "engine", ""), "invariant_results": inv,
            "outcome": outcome, "exposure": exposure, "has_proof": proof is not None}


def compute_metrics(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate flat records (from `_entry`) into the supervisor scorecard."""
    verdicts = {"allow": 0, "step_up": 0, "hold": 0, "block": 0}
    by_domain: Dict[str, int] = {}
    invariant_violations = 0
    verification_failures = 0
    unverified = 0
    financial_flagged = 0.0
    evidence_objects = 0
    requires_human = 0

    for e in entries:
        v = e.get("verdict", "")
        verdicts[v] = verdicts.get(v, 0) + 1
        by_domain[e.get("domain", "?")] = by_domain.get(e.get("domain", "?"), 0) + 1
        invariant_violations += sum(1 for ir in e.get("invariant_results", []) if not ir.get("satisfied", True))
        if e.get("outcome") == "failed":
            verification_failures += 1
        if e.get("outcome") in (None, "unknown"):
            unverified += 1
        if v in _NEEDS_HUMAN:
            requires_human += 1
        if e.get("has_proof"):
            evidence_objects += 1
        exp = e.get("exposure") or {}
        if v in _STOPS and isinstance(exp, dict) and exp.get("financial"):
            financial_flagged += float(exp["financial"])

    total = len(entries)
    return {
        "missions_observed": total,
        "actions_evaluated": total,
        "verdicts": verdicts,
        "requires_human": requires_human,
        "invariant_violations": invariant_violations,
        "verification_failures": verification_failures,          # API "succeeded", mission did not
        "unverified_or_unknown": unverified,
        "potential_incidents_prevented": verdicts["block"],       # dangerous actions blocked
        "financial_exposure_flagged": round(financial_flagged, 2),
        "evidence_objects_sealed": evidence_objects,
        "by_domain": by_domain,
        # honest N/A — need real timestamps / labeled ground truth to compute:
        "mean_time_to_verify": None,
        "false_positive_rate_estimate": None,
    }


@dataclass
class MetricsCollector:
    """Accumulate decisions live, then `snapshot()` the scorecard."""
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, response, proof=None) -> None:
        self.entries.append(_entry(response, proof))

    def record_result(self, result: Dict[str, Any]) -> None:
        """Convenience: record an assurance result dict {'response','proof'}."""
        self.record(result["response"], result.get("proof"))

    def snapshot(self) -> Dict[str, Any]:
        return compute_metrics(self.entries)
