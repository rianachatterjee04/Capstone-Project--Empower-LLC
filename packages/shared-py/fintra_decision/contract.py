"""The canonical Decision contract — the seam that makes "one core, many engines"
real. Every domain engine (Security today via Aegis; Finance/HR/Procurement next)
speaks the SAME DecisionRequest -> DecisionResponse, so a consequential action is
evaluated the same way no matter which engine owns it.

The model almost disappears: the request is Actor -> Action -> Target -> Context,
and the response is Verdict + Trust + Proof. Domain-neutral, zero external deps.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


# ── canonical verdict vocabulary ─────────────────────────────────────────────
class Verdict(str, Enum):
    ALLOW = "allow"      # proceed
    STEP_UP = "step_up"  # proceed with a second factor / second approver
    HOLD = "hold"        # hold for explicit human approval
    BLOCK = "block"      # deny


SEVERITY = {Verdict.ALLOW: 0, Verdict.STEP_UP: 1, Verdict.HOLD: 2, Verdict.BLOCK: 3}

# Every existing engine's NATIVE verdict, mapped to the canonical one. This is
# the concrete unification: Aegis says "deny_recommended", finance-signals say
# "require_approval", billpay says "step_up" — one vocabulary now.
_NATIVE_TO_CANONICAL = {
    # allow family (incl. Aegis PDP allow_with_logging)
    "allow": Verdict.ALLOW, "permit": Verdict.ALLOW, "approve": Verdict.ALLOW,
    "allow_with_logging": Verdict.ALLOW,
    # step-up family (incl. Aegis PDP require_step_up, finance-signals challenge)
    "challenge": Verdict.STEP_UP, "step_up": Verdict.STEP_UP, "stepup": Verdict.STEP_UP,
    "require_step_up": Verdict.STEP_UP, "verify": Verdict.STEP_UP,
    # hold family (incl. Aegis PDP human_review_required, finance-signals require_approval)
    "require_approval": Verdict.HOLD, "hold": Verdict.HOLD, "review": Verdict.HOLD,
    "needs_approval": Verdict.HOLD, "human_review_required": Verdict.HOLD,
    # block family (incl. Aegis PDP deny_recommended)
    "block": Verdict.BLOCK, "deny": Verdict.BLOCK, "deny_recommended": Verdict.BLOCK,
    "reject": Verdict.BLOCK, "denied": Verdict.BLOCK,
}


def normalize_verdict(native: str) -> Verdict:
    """Map any engine's native verdict to the canonical vocabulary. Unknown ->
    HOLD (fail-safe toward NOT proceeding, since these are consequential actions)."""
    return _NATIVE_TO_CANONICAL.get((native or "").strip().lower(), Verdict.HOLD)


def is_release(v: Verdict) -> bool:
    """Whether a verdict lets the action proceed (allow / step-up) vs stops it."""
    return v in (Verdict.ALLOW, Verdict.STEP_UP)


# ── trust band (from the Action Trust Score = 100 - risk) ────────────────────
class Band(str, Enum):
    TRUSTED = "trusted"
    GUARDED = "guarded"
    ELEVATED = "elevated"
    CRITICAL = "critical"


def band_from_score(score: float) -> Band:
    if score >= 80:
        return Band.TRUSTED
    if score >= 60:
        return Band.GUARDED
    if score >= 40:
        return Band.ELEVATED
    return Band.CRITICAL


# ── the request: Actor -> Action -> Target -> Context ────────────────────────
@dataclass
class Actor:
    id: str
    type: str = "agent"            # human | agent | service
    identity_confidence: float = 1.0
    privileged: bool = False


@dataclass
class Action:
    type: str                       # pay_invoice | issue_refund | run_payroll |
                                    # delete_iam_policy | deploy | merge_pr | ...
    verb: str = ""
    reversible: bool = True


@dataclass
class Target:
    id: str = ""
    kind: str = ""                  # invoice | vendor | iam_policy | deployment | ...
    environment: str = "prod"       # prod | staging | dev
    blast_radius: str = "team"      # enterprise | team | user


@dataclass
class DecisionContext:
    domain: str                     # finance | security | hr | procurement | ...
    amount: Optional[float] = None
    signals: List[Dict[str, Any]] = field(default_factory=list)
    envelope: Dict[str, Any] = field(default_factory=dict)   # engine-native advisory
    business: Dict[str, Any] = field(default_factory=dict)    # invoice/PO/approval, etc.


# ── Mission & Authority — the "why" and the "may" of a consequential action ───
# These make the spine domain-complete: every action can now carry WHY it is
# happening (Mission) and WHAT it is permitted to do (Authority), the two
# primitives the runtime audit found missing as first-class objects. Both are
# OPTIONAL (defaulted) so every existing caller keeps working unchanged.
@dataclass
class Mission:
    """Why this operation exists — bound to the action at decision time."""
    mission_id: str = ""
    intent: str = ""                       # human-readable purpose
    originating_signal: str = ""           # alert | human | schedule | agent
    objective: str = ""
    success_criteria: str = ""
    opened_by: str = ""
    ttl_seconds: Optional[int] = None
    status: str = "open"                   # open | achieved | failed | expired


@dataclass
class Authority:
    """What may be done for this mission — the scoped, expiring grant."""
    authority_id: str = ""
    monetary_limit: Optional[float] = None
    allowed_actions: List[str] = field(default_factory=list)
    prohibitions: List[str] = field(default_factory=list)
    expires_at: str = ""                   # ISO8601; empty = no time bound
    approval_required: bool = False
    delegated_from: str = ""               # the human/role that delegated it


@dataclass
class DecisionRequest:
    request_id: str
    actor: Actor
    action: Action
    target: Target
    context: DecisionContext
    org_id: str = ""          # canonical tenant — every decision is stamped to an org
    now_iso: str = ""
    mission: Optional[Mission] = None       # WHY (optional, back-compatible)
    authority: Optional[Authority] = None   # MAY  (optional, back-compatible)
    delegation: List["DelegationHop"] = field(default_factory=list)  # WHO delegated to WHOM


# ── the response: Verdict + Trust + Proof ────────────────────────────────────
def _seal(payload: Any) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass
class DecisionResponse:
    request_id: str
    domain: str
    engine: str
    verdict: Verdict
    trust_score: float               # 0..100 (Action Trust Score = 100 - risk)
    band: Band
    drivers: List[Dict[str, Any]] = field(default_factory=list)
    required_approvals: List[str] = field(default_factory=list)
    compensating_actions: List[str] = field(default_factory=list)
    explanation: str = ""
    invariant_results: List[Dict[str, Any]] = field(default_factory=list)  # which invariants held/failed
    evidence_ref: str = ""           # tamper-evident seal over the decision

    def sealed(self) -> "DecisionResponse":
        body = {k: v for k, v in asdict(self).items() if k != "evidence_ref"}
        self.evidence_ref = _seal(body)
        return self

    def to_ledger_row(self, request: "DecisionRequest") -> Dict[str, Any]:
        """The append-only enterprise-action-ledger row: a flat join of the
        request (who/what/where + tenant) and the decision (verdict + trust +
        proof). One shape to persist for every consequential action, whatever
        domain answered — the audit record behind the whole control plane."""
        return {
            "request_id": self.request_id,
            "org_id": request.org_id,
            "actor_identifier": request.actor.id,
            "actor_type": request.actor.type,
            "target_system_uri": request.target.id or request.target.kind,
            "target_environment": request.target.environment,
            "action_intent_signature": request.action.type,
            "functional_domain": self.domain,
            "calculated_blast_radius": request.target.blast_radius,
            "action_context_payload": {
                "amount": request.context.amount,
                "signals": request.context.signals,
                "business": request.context.business,
                "envelope": request.context.envelope,
                # WHY + MAY travel with every ledger row (no schema change: this
                # whole dict is persisted as record_json).
                "mission": asdict(request.mission) if request.mission else None,
                "authority": asdict(request.authority) if request.authority else None,
                "delegation": [asdict(h) for h in request.delegation],
                "invariant_results": self.invariant_results,
            },
            "enforced_decision": self.verdict.value,
            "trust_score": self.trust_score,
            "band": self.band.value,
            "engine": self.engine,
            "required_approvals": self.required_approvals,
            "compensating_actions": self.compensating_actions,
            "explanation": self.explanation,
            "evidence_ref": self.evidence_ref,
            "created_at": request.now_iso or None,
        }


# ── the rest of the canonical object model ───────────────────────────────────
# These complete the domain-neutral primitives from SENTRIAI_ARCHITECTURE.md §1.
# They are PURE dataclasses (no behaviour, no deps) that the invariant engine,
# the Proof Object, and future adapters compose. An AWS-IAM change and a Fintra
# payment must be two instances of the SAME primitives — so none of these fields
# is finance-specific or cloud-specific (opaque refs + typed dict payloads).

@dataclass
class State:
    """Before / proposed / expected / actual snapshot of a resource. The payloads
    are opaque dicts so this holds AWS/K8s/SaaS/finance/HR state alike."""
    resource_ref: str = ""
    before: Dict[str, Any] = field(default_factory=dict)
    proposed: Dict[str, Any] = field(default_factory=dict)
    expected: Dict[str, Any] = field(default_factory=dict)
    actual: Dict[str, Any] = field(default_factory=dict)
    captured_at: str = ""


@dataclass
class Policy:
    """A company policy (human intent → potentially enforceable rule)."""
    policy_id: str = ""
    source_doc: str = ""
    version: str = ""
    obligations: List[str] = field(default_factory=list)
    prohibitions: List[str] = field(default_factory=list)
    approvals: List[str] = field(default_factory=list)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    owner: str = ""
    approved_by: str = ""
    compiled_rule: str = ""            # set only after human review (policy compiler)


@dataclass
class Control:
    """A normalized control objective, framework-independent."""
    control_id: str = ""
    objective: str = ""
    type: str = "preventive"           # preventive | detective
    test_method: str = ""


@dataclass
class FrameworkMapping:
    """One control ↔ one framework reference (many-to-many crosswalk row)."""
    control_id: str = ""
    framework: str = ""                # SOC2 | ISO27001 | NIST_800_53 | SOX | ...
    ref: str = ""                      # e.g. "CC6.1", "AC-2", "CA-02"
    mapping_strength: str = "provisional"   # provisional | reviewed | authoritative


class Certainty(str, Enum):
    KNOWN = "known"            # deterministic, from a real dependency edge
    INFERRED = "inferred"      # reasoned, not certain
    SIMULATED = "simulated"    # from a model / what-if
    UNKNOWN = "unknown"        # we cannot say


@dataclass
class Exposure:
    """Consequence & Exposure — business impact, not only cybersecurity blast radius.
    An action can be technically authorized yet carry $1.8M of exposure and be
    irreversible → escalate. Any dimension may be None (unknown, not zero)."""
    financial: Optional[float] = None          # $ at risk / directed
    customers_affected: Optional[int] = None
    employees_affected: Optional[int] = None
    security: str = ""                          # qualitative note per dimension
    operational: str = ""
    compliance: str = ""
    safety: str = ""
    reputational: str = ""
    reversibility: str = "unknown"              # reversible | partial | irreversible | unknown


@dataclass
class Consequence:
    """Predicted + observed downstream impact of an action. `certainty` MUST NOT
    present inference as fact (architecture rule); `exposure` carries the business
    dimensions (Consequence & Exposure)."""
    blast_radius_score: float = 0.0
    impacted: List[Dict[str, Any]] = field(default_factory=list)   # identity→app→api→resource→$
    predicted: str = ""
    observed: str = ""
    certainty: Certainty = Certainty.UNKNOWN
    exposure: Optional[Exposure] = None


@dataclass
class Outcome:
    """Did the mission actually succeed — independent of an API returning 200."""
    status: str = "unknown"            # succeeded | failed | partial | unknown
    verification_method: str = ""
    unintended: List[str] = field(default_factory=list)


@dataclass
class Exception:
    """A governed deviation with a lifecycle (justify → approve → expire/verify)."""
    exception_id: str = ""
    control_ids: List[str] = field(default_factory=list)
    justification: str = ""
    compensating_controls: List[str] = field(default_factory=list)
    risk: str = ""
    approval_status: str = "pending"   # pending | approved | rejected | risk_accepted
    starts_at: str = ""
    expires_at: str = ""
    verification_result: str = ""


@dataclass
class Recovery:
    """A compensation plan — NOT just 'restore snapshot'. Business recovery may
    require compensating transactions and can have irreversible parts."""
    recovery_id: str = ""
    reversible: bool = True
    rollback_mechanism: str = ""
    compensating_actions: List[str] = field(default_factory=list)
    irreversible_consequences: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    requires_human: bool = False
    status: str = "planned"            # planned | executing | done | failed


@dataclass
class DelegationHop:
    """One link in the provenance/delegation chain — WHO actually authorized WHAT.
    Autonomous work runs Human → Agent A → Agent B → MCP tool → API → System; each
    hop may narrow (never widen) the permissions and limits it was delegated."""
    principal_id: str
    kind: str = "agent"            # human | agent | service | tool | model | api | process
    acted_as: str = ""             # role/identity assumed at this hop
    model: str = ""                # model/provider (kind in agent|model)
    tool: str = ""                 # tool / MCP server (kind == tool)
    delegated_permissions: List[str] = field(default_factory=list)
    limits: Dict[str, Any] = field(default_factory=dict)   # monetary/time/scope caps here
    mission_modified: bool = False # did this hop change the mission intent?
    note: str = ""
