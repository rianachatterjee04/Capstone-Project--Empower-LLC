"""Policy compiler — human policy → candidate enforceable rule, human-reviewed.

Company policy is prose ("Production IAM changes must be approved by someone other
than the initiating principal"). This proposes a *candidate* machine-enforceable
rule and carries it through an explicit lifecycle:

    DRAFT → REVIEWED → APPROVED → ACTIVE → RETIRED

The one rule that matters: **a compiled rule is never authoritative until a human
approves it.** `compile_policy` only ever returns a DRAFT, with the source policy,
the candidate rule, a plain-language interpretation, a heuristic confidence, the
affected controls/frameworks, the assumptions it made, and a source reference. It
is *not* an LLM (deterministic pattern match here) — and even a real LLM version
must stop at DRAFT and require human review before it can enforce anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PolicyState(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    ACTIVE = "active"
    RETIRED = "retired"


class PolicyLifecycleError(Exception):
    """Illegal state transition (e.g. activating something never approved)."""


@dataclass
class PolicyDraft:
    policy_id: str
    source_policy: str                       # the human text (verbatim)
    candidate_rule: str                      # the proposed invariant rule name (or "")
    interpretation: str                      # plain-language reading
    confidence: float                        # 0..1 heuristic (NOT a guarantee)
    affected_controls: List[str] = field(default_factory=list)
    framework_refs: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    source_reference: str = ""
    version: int = 1
    state: PolicyState = PolicyState.DRAFT
    reviewer: str = ""
    approver: str = ""
    effective_date: str = ""                 # ISO date; set at approval

    # ── lifecycle (never skip a step; never silently activate) ───────────────
    def review(self, reviewer: str, *, edited_rule: Optional[str] = None) -> "PolicyDraft":
        if self.state != PolicyState.DRAFT:
            raise PolicyLifecycleError(f"can only review a DRAFT (was {self.state.value})")
        if not reviewer:
            raise PolicyLifecycleError("a reviewer is required")
        if edited_rule is not None:          # a human may correct the candidate rule
            self.candidate_rule = edited_rule
            self.version += 1
        self.reviewer = reviewer
        self.state = PolicyState.REVIEWED
        return self

    def approve(self, approver: str, effective_date: str) -> "PolicyDraft":
        if self.state != PolicyState.REVIEWED:
            raise PolicyLifecycleError(f"can only approve a REVIEWED policy (was {self.state.value})")
        if not approver or not effective_date:
            raise PolicyLifecycleError("an approver and an effective_date are required")
        self.approver = approver
        self.effective_date = effective_date
        self.state = PolicyState.APPROVED
        return self

    def activate(self) -> "PolicyDraft":
        if self.state != PolicyState.APPROVED:
            raise PolicyLifecycleError("only an APPROVED policy can go ACTIVE")
        self.state = PolicyState.ACTIVE
        return self

    def retire(self) -> "PolicyDraft":
        self.state = PolicyState.RETIRED
        return self

    def is_enforceable(self) -> bool:
        """True ONLY when ACTIVE and it has a reviewer + approver + effective date.
        The invariant engine must gate on this — never enforce a DRAFT/unreviewed rule."""
        return (self.state == PolicyState.ACTIVE and bool(self.reviewer)
                and bool(self.approver) and bool(self.effective_date))


# ── deterministic pattern → candidate rule (a real LLM would replace this,
#    but must still stop at DRAFT) ───────────────────────────────────────────
_PATTERNS = [
    (r"(independent approv|someone other than|separate approver|cannot approve (their|its) own|"
     r"segregation of dut)", "sod_actor_not_approver", "finance.sod / security SoD",
     ["CC-NATIVE-SOD"], ["SOX CE-03", "SOC2 CC6.3"],
     "The initiator of an action cannot also approve it."),
    (r"(disabl\w*\s+(multi-?factor|mfa)|(multi-?factor|\bmfa\b).*(requir|prohibit|must)|"
     r"(requir|prohibit|must).*(multi-?factor|\bmfa\b))",
     "no_disable_required_mfa", "security MFA", ["IA-002"], ["NIST 800-53 IA-2", "CIS 6.3"],
     "MFA must not be disabled on privileged principals."),
    (r"(wildcard|full admin|\*:\*|admin.*(all|everything))", "no_wildcard_admin",
     "security least-privilege", ["AC-006"], ["NIST 800-53 AC-6", "CIS 5.4"],
     "No policy may grant wildcard admin (Action '*' on Resource '*')."),
    (r"(break[- ]?glass|at least (two|2|\d+) admin|minimum .* admin)", "min_break_glass_admins",
     "security break-glass", ["AC-002"], ["NIST 800-53 AC-2", "CIS 5.4"],
     "A minimum number of break-glass admins must remain."),
    (r"(public|0\.0\.0\.0/0|internet-facing|publicly accessible)", "no_public_exposure",
     "security exposure", ["SC-007"], ["NIST 800-53 SC-7", "PCI DSS 1.3"],
     "Protected resources must not become publicly accessible."),
    (r"(payment|spend|disburse|wire).*(exceed|over|above|more than|approv)|approv.*(payment|amount)",
     "payment_has_required_approvals", "finance approval", ["CC-NATIVE-APPROVAL"],
     ["SOX CA-01", "SOC2 CC6.1"], "Payments require their approval chain (and cannot exceed the approved amount)."),
]

_AMOUNT = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(k|thousand|m|million)?", re.I)


def _extract_threshold(text: str) -> Optional[float]:
    m = _AMOUNT.search(text)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit in ("k", "thousand"):
        val *= 1_000
    elif unit in ("m", "million"):
        val *= 1_000_000
    return val


def compile_policy(text: str, *, policy_id: str = "", source_reference: str = "") -> PolicyDraft:
    """Propose a candidate enforceable rule for a human policy. ALWAYS returns a
    DRAFT — a human must review/approve/activate before it can enforce anything."""
    lowered = (text or "").lower()
    for pattern, rule, interp_scope, controls, frameworks, interp in _PATTERNS:
        if re.search(pattern, lowered):
            params = {}
            conf = 0.7
            assumptions = [f"Mapped by keyword pattern to '{rule}' ({interp_scope}); a human must confirm the mapping."]
            if rule == "payment_has_required_approvals":
                thr = _extract_threshold(text)
                if thr is not None:
                    params = {"threshold": thr}
                    assumptions.append(f"Read an approval threshold of ${thr:,.0f}.")
            if rule == "min_break_glass_admins":
                mn = re.search(r"at least (\d+)|minimum (\d+)|(two|2)", lowered)
                params = {"min": int(mn.group(1) or mn.group(2)) if (mn and (mn.group(1) or mn.group(2))) else 2}
            return PolicyDraft(policy_id=policy_id or f"pol:{abs(hash(text)) % 10_000_000}",
                               source_policy=text, candidate_rule=rule, interpretation=interp,
                               confidence=conf, affected_controls=controls, framework_refs=frameworks,
                               assumptions=assumptions, params=params, source_reference=source_reference)
    # no known pattern → a DRAFT that needs a human to author the rule (honest)
    return PolicyDraft(policy_id=policy_id or f"pol:{abs(hash(text)) % 10_000_000}",
                       source_policy=text, candidate_rule="", interpretation="No known rule pattern matched.",
                       confidence=0.2, affected_controls=[], framework_refs=[],
                       assumptions=["No keyword pattern matched; a human must author the enforceable rule."],
                       source_reference=source_reference)
