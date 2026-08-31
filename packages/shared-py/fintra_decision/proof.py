"""The Proof Object — SentriAI's core product artifact.

Every governed machine mission should be capable of producing ONE sealed,
independently verifiable record that binds the entire chain:

  mission → initiating principal → executing principal → authority → policy →
  controls → framework refs → approvals → before-state → proposed action →
  actual action → after-state → invariant results → outcome → exceptions →
  recovery → evidence integrity → timestamps.

This is what an auditor, an internal security/compliance team, and eventually an
external trust consumer inspect. Pure + dependency-free (same discipline as the
rest of `fintra_decision`): `seal()` content-addresses the object, `verify()`
recomputes and detects tampering.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .contract import (
    Actor,
    Authority,
    Consequence,
    DecisionRequest,
    DecisionResponse,
    Mission,
    Outcome,
    Recovery,
    State,
)
from .invariants import InvariantResult


def _seal(payload: Any) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass
class ProofObject:
    proof_id: str
    org_id: str
    domain: str
    # WHY / WHO
    mission: Optional[Dict[str, Any]] = None
    initiating_principal: str = ""
    executing_principal: str = ""
    authority: Optional[Dict[str, Any]] = None
    # WHAT applied
    policy_version: str = ""
    controls: List[str] = field(default_factory=list)
    framework_refs: List[str] = field(default_factory=list)
    approvals: List[str] = field(default_factory=list)
    # STATE + ACTION
    before_state: Optional[Dict[str, Any]] = None
    proposed_action: Dict[str, Any] = field(default_factory=dict)
    actual_action: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    # JUDGEMENT
    invariant_results: List[Dict[str, Any]] = field(default_factory=list)
    verdict: str = ""
    trust_score: float = 0.0
    consequence: Optional[Dict[str, Any]] = None
    outcome: Optional[Dict[str, Any]] = None
    exceptions: List[Dict[str, Any]] = field(default_factory=list)
    recovery: Optional[Dict[str, Any]] = None
    # INTEGRITY
    decision_evidence_ref: str = ""       # the sealed decision this proof extends
    prev_proof_hash: str = ""             # optional chain to the previous proof
    sealed_at: str = ""
    integrity: str = ""                   # the seal over everything above

    def seal(self) -> "ProofObject":
        body = {k: v for k, v in asdict(self).items() if k != "integrity"}
        self.integrity = _seal(body)
        return self

    def verify(self) -> bool:
        body = {k: v for k, v in asdict(self).items() if k != "integrity"}
        return self.integrity == _seal(body)


def build_proof(
    request: DecisionRequest,
    response: DecisionResponse,
    *,
    invariant_results: Optional[List[InvariantResult]] = None,
    before_state: Optional[State] = None,
    after_state: Optional[State] = None,
    actual_action: Optional[Dict[str, Any]] = None,
    consequence: Optional[Consequence] = None,
    outcome: Optional[Outcome] = None,
    recovery: Optional[Recovery] = None,
    exceptions: Optional[List[Dict[str, Any]]] = None,
    policy_version: str = "",
    prev_proof_hash: str = "",
    sealed_at: str = "",
) -> ProofObject:
    """Compose a sealed Proof Object from a request + its sealed decision, folding
    in whatever verification/state/recovery is known. Controls + framework refs are
    aggregated from the invariant results (deduped), so a breach's conformance
    mapping is captured in the proof."""
    ir = invariant_results or []
    controls: List[str] = []
    frameworks: List[str] = []
    for r in ir:
        for c in r.control_refs:
            if c not in controls:
                controls.append(c)
        for f in r.framework_refs:
            if f not in frameworks:
                frameworks.append(f)

    proof = ProofObject(
        proof_id=f"proof:{request.org_id or 'none'}:{request.request_id}",
        org_id=request.org_id,
        domain=response.domain,
        mission=asdict(request.mission) if request.mission else None,
        initiating_principal=(request.mission.opened_by if request.mission else "") or request.actor.id,
        executing_principal=request.actor.id,
        authority=asdict(request.authority) if request.authority else None,
        policy_version=policy_version,
        controls=controls,
        framework_refs=frameworks,
        approvals=list(response.required_approvals),
        before_state=asdict(before_state) if before_state else None,
        proposed_action={"type": request.action.type, "target": request.target.id,
                         "environment": request.target.environment,
                         "amount": request.context.amount},
        actual_action=actual_action,
        after_state=asdict(after_state) if after_state else None,
        invariant_results=[asdict(r) for r in ir],
        verdict=response.verdict.value,
        trust_score=response.trust_score,
        consequence=asdict(consequence) if consequence else None,
        outcome=asdict(outcome) if outcome else None,
        exceptions=exceptions or [],
        recovery=asdict(recovery) if recovery else None,
        decision_evidence_ref=response.evidence_ref,
        prev_proof_hash=prev_proof_hash,
        sealed_at=sealed_at or request.now_iso,
    )
    return proof.seal()
