"""Compliance becomes operational — Proof of Control Operation from the action stream.

Vanta/Drata collect evidence by asking "do you have MFA?" once a quarter. SentriAI
computes control state *continuously from what machines actually did*: every governed
decision seals a Proof Object whose invariant results already carry the normalized
`control_refs` (canonical control objectives) and `framework_refs` (the many-to-many
crosswalk). This module folds that stream into:

  framework → control → (each execution) → pass/fail → effectiveness → live health,
  with the evidence (proof hashes) that backs every count.

So a control's status is not a self-attestation — it is *"this control was exercised
N times by real actions this period; it operated M times; here is the evidence."*
Pure + deterministic. Consumes the Proof Objects the domains already produce.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _iter_invariant_results(proof: Any):
    """Yield the invariant-result dicts from a ProofObject (or a plain dict)."""
    irs = getattr(proof, "invariant_results", None)
    if irs is None and isinstance(proof, dict):
        irs = proof.get("invariant_results")
    return irs or []


def _integrity(proof: Any) -> str:
    return getattr(proof, "integrity", None) or (proof.get("integrity") if isinstance(proof, dict) else "") or ""


def _health(effectiveness: float, failed: int) -> str:
    if failed == 0:
        return "operating"
    if effectiveness > 0:
        return "degraded"
    return "failing"


def compute_control_operation(proofs: List[Any]) -> Dict[str, Any]:
    """Fold sealed Proof Objects into per-control and per-framework operation state."""
    controls: Dict[str, Dict[str, Any]] = {}
    for proof in proofs:
        ev = _integrity(proof)
        for ir in _iter_invariant_results(proof):
            satisfied = bool(ir.get("satisfied", True))
            frameworks = ir.get("framework_refs", []) or []
            for c in ir.get("control_refs", []) or []:
                rec = controls.setdefault(c, {"control_id": c, "executions": 0, "passed": 0,
                                              "failed": 0, "frameworks": set(), "evidence_refs": []})
                rec["executions"] += 1
                rec["passed" if satisfied else "failed"] += 1
                rec["frameworks"].update(frameworks)
                if ev and ev not in rec["evidence_refs"]:
                    rec["evidence_refs"].append(ev)

    control_out: Dict[str, Any] = {}
    for cid, rec in sorted(controls.items()):
        eff = round(100.0 * rec["passed"] / rec["executions"], 1) if rec["executions"] else 0.0
        control_out[cid] = {**rec, "frameworks": sorted(rec["frameworks"]),
                            "effectiveness_pct": eff, "health": _health(eff, rec["failed"])}

    # framework roll-up: normalize once (canonical control), prove to many frameworks
    frameworks: Dict[str, Dict[str, Any]] = {}
    for cid, rec in control_out.items():
        for fw in rec["frameworks"]:
            f = frameworks.setdefault(fw, {"framework": fw, "controls": set(),
                                           "executions": 0, "passed": 0, "failed": 0})
            f["controls"].add(cid)
            f["executions"] += rec["executions"]
            f["passed"] += rec["passed"]
            f["failed"] += rec["failed"]
    framework_out: Dict[str, Any] = {}
    for fw, f in sorted(frameworks.items()):
        eff = round(100.0 * f["passed"] / f["executions"], 1) if f["executions"] else 0.0
        framework_out[fw] = {"framework": fw, "controls": sorted(f["controls"]),
                             "control_count": len(f["controls"]), "executions": f["executions"],
                             "operating_pct": eff, "health": _health(eff, f["failed"])}

    total_exec = sum(r["executions"] for r in control_out.values())
    total_pass = sum(r["passed"] for r in control_out.values())
    return {
        "controls": control_out,
        "frameworks": framework_out,
        "summary": {"controls_exercised": len(control_out),
                    "frameworks_touched": len(framework_out),
                    "total_executions": total_exec,
                    "overall_effectiveness_pct": round(100.0 * total_pass / total_exec, 1) if total_exec else 0.0,
                    "failing_controls": [c for c, r in control_out.items() if r["health"] == "failing"]},
    }
