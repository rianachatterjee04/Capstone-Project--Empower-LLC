"""The Business/Security Invariant engine — a first-class, reusable primitive.

An **Invariant** is a machine-checkable "must always remain true" (e.g. *the actor
who changed a vendor's bank cannot also release that vendor's payment*; *at least 2
break-glass admins must remain*). This is one of SentriAI's core differentiators:
invariants are declarative + data-driven (serializable), evaluated by a pluggable
registry of pure evaluators, and every violation carries its **verdict floor** plus
the **controls and framework references** it maps to — so a breach flows straight
into decision → evidence → control status → framework conformance.

Domain-neutral: finance and security invariants are the same shape, evaluated over
a neutral `context` dict. Adding a domain = registering evaluators, not reshaping.

Framework/control refs on the shipped invariants are **provisional** crosswalks
(`mapping_strength="provisional"`) — not authoritative legal interpretations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .contract import SEVERITY, Verdict


# ── schema ───────────────────────────────────────────────────────────────────
@dataclass
class Invariant:
    invariant_id: str                  # stable id; also the driver label suffix
    scope: str                         # finance | security | ...
    statement: str                     # human-readable "must always be true"
    rule: str                          # registry key of the evaluator
    severity: Verdict = Verdict.HOLD   # the verdict FLOOR imposed when violated
    params: Dict[str, Any] = field(default_factory=dict)
    owner: str = ""
    control_refs: List[str] = field(default_factory=list)     # canonical control ids
    framework_refs: List[str] = field(default_factory=list)   # "SOC2 CC6.1", "NIST 800-53 AC-2"
    policy_refs: List[str] = field(default_factory=list)


@dataclass
class InvariantResult:
    invariant_id: str
    scope: str
    statement: str
    satisfied: bool
    severity: Verdict                  # floor imposed if not satisfied
    detail: str = ""
    control_refs: List[str] = field(default_factory=list)
    framework_refs: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.invariant_id.split(".")[-1]


# evaluator signature: (params, context) -> (satisfied: bool, detail: str)
Evaluator = Callable[[Dict[str, Any], Dict[str, Any]], Tuple[bool, str]]
_REGISTRY: Dict[str, Evaluator] = {}


def register(name: str) -> Callable[[Evaluator], Evaluator]:
    def deco(fn: Evaluator) -> Evaluator:
        _REGISTRY[name] = fn
        return fn
    return deco


class InvariantEngine:
    """Evaluates a set of invariants against a neutral context. Fail-safe: an
    unknown rule or a raising evaluator is treated as NOT satisfied (never a
    silent pass), because these are consequential actions."""

    def __init__(self, registry: Optional[Dict[str, Evaluator]] = None) -> None:
        self._reg = registry if registry is not None else _REGISTRY

    def evaluate(self, invariants: List[Invariant], context: Dict[str, Any]) -> List[InvariantResult]:
        out: List[InvariantResult] = []
        for inv in invariants:
            fn = self._reg.get(inv.rule)
            if fn is None:
                out.append(InvariantResult(inv.invariant_id, inv.scope, inv.statement,
                                           False, Verdict.HOLD, f"no evaluator '{inv.rule}'",
                                           inv.control_refs, inv.framework_refs))
                continue
            try:
                satisfied, detail = fn(inv.params, context)
            except Exception as e:  # a bad evaluator must never crash the decision
                satisfied, detail = False, f"evaluator error: {e}"
            out.append(InvariantResult(inv.invariant_id, inv.scope, inv.statement,
                                       bool(satisfied), inv.severity, detail,
                                       inv.control_refs, inv.framework_refs))
        return out

    @staticmethod
    def verdict_floor(results: List[InvariantResult]) -> Verdict:
        """The worst floor imposed by any VIOLATED invariant."""
        floor = Verdict.ALLOW
        for r in results:
            if not r.satisfied and SEVERITY[r.severity] > SEVERITY[floor]:
                floor = r.severity
        return floor

    @staticmethod
    def violations(results: List[InvariantResult]) -> List[InvariantResult]:
        return [r for r in results if not r.satisfied]


# ── initial FINANCE invariants (evaluators) ──────────────────────────────────
@register("sod_actor_not_approver")
def _sod(params, ctx):
    creator, approver = ctx.get("created_by"), ctx.get("approved_by")
    if creator and approver and creator == approver:
        return False, f"Segregation of duties: creator and approver are the same principal ({creator})."
    return True, "Creator and approver are distinct."


@register("vendor_bank_unchanged_or_reverified")
def _vendor_bank(params, ctx):
    prior, new = ctx.get("prior_bank"), ctx.get("new_bank")
    if prior and new and prior != new and not ctx.get("bank_reverified"):
        return False, "Vendor payout bank changed since the last payment and was not re-verified."
    return True, "No unverified vendor-bank change."


@register("payment_within_approved_amount")
def _within_amount(params, ctx):
    amount, approved = ctx.get("amount"), ctx.get("approved_amount")
    if amount is not None and approved is not None and float(amount) > float(approved):
        return False, f"Payment ${float(amount):,.0f} exceeds the approved amount ${float(approved):,.0f}."
    return True, "Payment within the approved amount."


@register("payment_has_required_approvals")
def _has_approvals(params, ctx):
    required = set(ctx.get("required_approvers") or [])
    have = set(ctx.get("approvals") or [])
    missing = required - have
    if missing:
        return False, f"Missing required approval(s): {', '.join(sorted(missing))}."
    return True, "Required approval chain present."


@register("action_within_authority")
def _within_authority(params, ctx):
    allowed = ctx.get("authority_allowed_actions")
    action = ctx.get("action_type")
    if allowed and action and action not in allowed:
        return False, f"Action '{action}' is outside the delegated authority scope."
    limit, amount = ctx.get("authority_limit"), ctx.get("amount")
    if limit is not None and amount is not None and float(amount) > float(limit):
        return False, f"Amount ${float(amount):,.0f} exceeds delegated authority ${float(limit):,.0f}."
    return True, "Action within delegated authority."


# ── initial SECURITY invariants (evaluators) ─────────────────────────────────
@register("min_break_glass_admins")
def _break_glass(params, ctx):
    if not ctx.get("removes_admin_from"):
        return True, "No admin removal."
    minimum = int(params.get("min", 2))
    remaining = int(ctx.get("remaining_break_glass_admins", minimum))
    if remaining < minimum:
        return False, f"Would leave {remaining} break-glass admin(s); requires ≥ {minimum}."
    return True, f"{remaining} break-glass admins remain (≥ {minimum})."


@register("no_wildcard_admin")
def _no_wildcard(params, ctx):
    for s in ctx.get("statements") or []:
        if str(s.get("effect", "Allow")).lower() != "allow":
            continue
        actions = [str(a) for a in (s.get("actions") or [])]
        resources = [str(r) for r in (s.get("resources") or [])]
        if "*" in actions and "*" in resources:
            return False, "Policy grants Action '*' on Resource '*' (full admin)."
    return True, "No wildcard-admin grant."


@register("no_disable_required_mfa")
def _no_mfa_disable(params, ctx):
    disabling = ctx.get("action_type") == "disable_mfa" or ctx.get("disables_mfa")
    if disabling and ctx.get("mfa_target_privileged"):
        return False, "Disabling MFA on a privileged principal."
    return True, "No required-MFA disablement."


@register("no_public_exposure")
def _no_public(params, ctx):
    public = {"0.0.0.0/0", "::/0"}
    if ctx.get("action_type") == "make_bucket_public" or str(ctx.get("opens_cidr", "")).strip() in public:
        return False, f"Opens a resource to the public ({ctx.get('opens_cidr') or 'public-read'})."
    return True, "No public exposure."


# ── provisional control / framework crosswalk for the shipped invariants ─────
# Provisional mappings (mapping_strength="provisional") — validate before claiming
# authoritative conformance. Keyed by invariant_id suffix.
CROSSWALK: Dict[str, Dict[str, List[str]]] = {
    "sod_actor_not_approver": {"controls": ["CC-NATIVE-SOD"],
                               "frameworks": ["SOX CE-03", "SOC2 CC6.3", "NIST 800-53 AC-5"]},
    "vendor_bank_unchanged_or_reverified": {"controls": ["CC-NATIVE-VENDOR-BANK"],
                               "frameworks": ["SOX CA-02", "SOC2 CC6.1"]},
    "payment_within_approved_amount": {"controls": ["CC-NATIVE-LIMIT"],
                               "frameworks": ["SOX CA-04", "SOC2 CC6.1"]},
    "payment_has_required_approvals": {"controls": ["CC-NATIVE-APPROVAL"],
                               "frameworks": ["SOX CA-01", "SOC2 CC6.1"]},
    "action_within_authority": {"controls": ["AC-006"],
                               "frameworks": ["NIST 800-53 AC-6", "SOC2 CC6.1"]},
    "min_break_glass_admins": {"controls": ["AC-002"],
                               "frameworks": ["NIST 800-53 AC-2", "CIS 5.4", "SOC2 CC6.1"]},
    "no_wildcard_admin": {"controls": ["AC-006"],
                               "frameworks": ["NIST 800-53 AC-6", "SOC2 CC6.1", "CIS 5.4"]},
    "no_disable_required_mfa": {"controls": ["IA-002"],
                               "frameworks": ["NIST 800-53 IA-2", "SOC2 CC6.1", "CIS 6.3"]},
    "no_public_exposure": {"controls": ["SC-007"],
                               "frameworks": ["NIST 800-53 SC-7", "SOC2 CC6.6", "PCI DSS 1.3"]},
}


def _refs(rule: str) -> Tuple[List[str], List[str]]:
    cw = CROSSWALK.get(rule, {})
    return list(cw.get("controls", [])), list(cw.get("frameworks", []))


def _inv(invariant_id, scope, statement, rule, severity, **kw) -> Invariant:
    controls, frameworks = _refs(rule)
    return Invariant(invariant_id=invariant_id, scope=scope, statement=statement,
                     rule=rule, severity=severity, control_refs=controls,
                     framework_refs=frameworks, **kw)


def finance_invariants() -> List[Invariant]:
    return [
        _inv("finance.sod_actor_not_approver", "finance",
             "The actor who created a transaction cannot also approve it.",
             "sod_actor_not_approver", Verdict.HOLD),
        _inv("finance.vendor_bank_unchanged_or_reverified", "finance",
             "A vendor's payout bank cannot change unverified before a payment.",
             "vendor_bank_unchanged_or_reverified", Verdict.HOLD),
        _inv("finance.payment_within_approved_amount", "finance",
             "A payment cannot exceed its approved amount.",
             "payment_within_approved_amount", Verdict.BLOCK),
        _inv("finance.payment_has_required_approvals", "finance",
             "A payment must carry its required approval chain.",
             "payment_has_required_approvals", Verdict.HOLD),
        _inv("finance.action_within_authority", "finance",
             "An action cannot exceed the delegated authority (scope or amount).",
             "action_within_authority", Verdict.HOLD),
    ]


def security_invariants(*, prod: bool = True, enterprise_blast: bool = False) -> List[Invariant]:
    """Severity is set per-request where the environment matters (prod vs not,
    enterprise blast vs not) — the engine builds the set for each decision."""
    wildcard_sev = Verdict.BLOCK if prod else Verdict.HOLD
    public_sev = Verdict.BLOCK if enterprise_blast else Verdict.HOLD
    return [
        _inv("security.min_break_glass_admins", "security",
             "A change must leave at least N break-glass admins available.",
             "min_break_glass_admins", Verdict.BLOCK, params={"min": 2}),
        _inv("security.no_wildcard_admin", "security",
             "A change cannot grant wildcard admin (Action '*' on Resource '*').",
             "no_wildcard_admin", wildcard_sev),
        _inv("security.no_disable_required_mfa", "security",
             "A change cannot disable MFA on a privileged principal.",
             "no_disable_required_mfa", Verdict.BLOCK),
        _inv("security.no_public_exposure", "security",
             "A change cannot make a protected resource publicly accessible.",
             "no_public_exposure", public_sev),
        _inv("security.action_within_authority", "security",
             "An action cannot exceed the mission's authorized scope.",
             "action_within_authority", Verdict.HOLD),
    ]
