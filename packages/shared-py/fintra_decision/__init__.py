"""fintra_decision — the canonical Decision contract.

One request shape (Actor -> Action -> Target -> Context), one response shape
(Verdict + Trust + Proof), one verdict vocabulary, many domain engines. This is
the seam that makes "one core, many engines" real: Security (Aegis PDP) and
Finance (evaluate_payment) become engines behind the SAME contract, and adding a
domain is registering an engine — not reshaping the contract.
"""
from .contract import (
    Action,
    Actor,
    Authority,
    Band,
    Certainty,
    Consequence,
    Control,
    DecisionContext,
    DecisionRequest,
    DecisionResponse,
    DelegationHop,
    Exception as GovernedException,
    Exposure,
    FrameworkMapping,
    Mission,
    Outcome,
    Policy,
    Recovery,
    SEVERITY,
    State,
    Target,
    Verdict,
    band_from_score,
    is_release,
    normalize_verdict,
)
from .delegation import (
    executing_principal,
    originating_principal,
    validate_delegation,
)
from .compliance import compute_control_operation
from .engine import DecisionEngine, DecisionRegistry, NoEngineError
from .exposure import assess_exposure, exposure_escalation
from .graph import Edge, Impact, Node, RELATIONS, StateGraph
from .invariants import (
    Invariant,
    InvariantEngine,
    InvariantResult,
    finance_invariants,
    register,
    security_invariants,
)
from .ledger import LedgerSink, idempotency_key_for, persist_decision
from .metrics import MetricsCollector, compute_metrics
from .policy_compiler import PolicyDraft, PolicyLifecycleError, PolicyState, compile_policy
from .proof import ProofObject, build_proof
from .recovery import plan_recovery, register_recovery
from .verification import OutcomeCheck, verify_outcome
from .reference import (
    FinanceDecisionEngine,
    SecurityDecisionEngine,
    default_registry,
)

__all__ = [
    "Verdict",
    "Band",
    "SEVERITY",
    "normalize_verdict",
    "is_release",
    "band_from_score",
    "Actor",
    "Action",
    "Target",
    "Mission",
    "Authority",
    "State",
    "Policy",
    "Control",
    "FrameworkMapping",
    "Consequence",
    "Certainty",
    "Exposure",
    "Outcome",
    "GovernedException",
    "Recovery",
    "DelegationHop",
    "validate_delegation",
    "originating_principal",
    "executing_principal",
    "Node",
    "Edge",
    "Impact",
    "StateGraph",
    "RELATIONS",
    "Invariant",
    "InvariantEngine",
    "InvariantResult",
    "register",
    "finance_invariants",
    "security_invariants",
    "ProofObject",
    "build_proof",
    "OutcomeCheck",
    "verify_outcome",
    "plan_recovery",
    "register_recovery",
    "assess_exposure",
    "exposure_escalation",
    "MetricsCollector",
    "compute_metrics",
    "compute_control_operation",
    "compile_policy",
    "PolicyDraft",
    "PolicyState",
    "PolicyLifecycleError",
    "DecisionContext",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionEngine",
    "DecisionRegistry",
    "NoEngineError",
    "LedgerSink",
    "persist_decision",
    "idempotency_key_for",
    "FinanceDecisionEngine",
    "SecurityDecisionEngine",
    "default_registry",
]

__version__ = "0.1.0"
