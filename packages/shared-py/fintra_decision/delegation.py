"""Delegation / provenance chain validation — a first-class spine primitive.

Autonomous work runs Human → Agent A → Agent B → MCP tool → API → System. The
core question SentriAI answers is *who actually authorized what*. A valid chain
must **narrow, never widen**: each hop's delegated permissions must be a subset of
its parent's, its monetary/scope limits must not exceed the parent's, and a hop
that silently modifies the mission is a red flag.

Pure + dependency-free. Returns (ok, issues) so a decision engine can fold chain
integrity into its verdict and evidence.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .contract import DelegationHop


def validate_delegation(chain: List[DelegationHop]) -> Tuple[bool, List[str]]:
    """Check that a delegation chain narrows and never widens authority.

    Rules:
      1. Permissions at hop N must be a subset of hop N-1's (a hop cannot grant
         itself a permission it wasn't delegated). An empty parent permission set
         is treated as 'unspecified' and not enforced (can't prove a subset).
      2. A numeric limit (e.g. monetary) at hop N must not exceed hop N-1's.
      3. A hop that modifies the mission is flagged (not fatal, but surfaced).
    """
    issues: List[str] = []
    for i in range(1, len(chain)):
        parent, child = chain[i - 1], chain[i]

        if parent.delegated_permissions:
            parent_perms = set(parent.delegated_permissions)
            extra = set(child.delegated_permissions) - parent_perms
            if extra:
                issues.append(
                    f"hop {i} ({child.principal_id}) widened permissions beyond "
                    f"{parent.principal_id}: {sorted(extra)}")

        for key, cval in (child.limits or {}).items():
            pval = (parent.limits or {}).get(key)
            if isinstance(cval, (int, float)) and isinstance(pval, (int, float)) and cval > pval:
                issues.append(
                    f"hop {i} ({child.principal_id}) limit '{key}'={cval} exceeds "
                    f"parent {parent.principal_id} '{key}'={pval}")

        if child.mission_modified:
            issues.append(f"hop {i} ({child.principal_id}) modified the mission")

    return (len([x for x in issues if "modified the mission" not in x]) == 0, issues)


def originating_principal(chain: List[DelegationHop]) -> str:
    """The human/business process at the root of the chain (or '')."""
    return chain[0].principal_id if chain else ""


def executing_principal(chain: List[DelegationHop]) -> str:
    """The identity that actually performs the action (leaf of the chain, or '')."""
    return chain[-1].principal_id if chain else ""
