"""Outcome verification — one reusable, domain-neutral module.

A successful API call is NOT a successful mission. Every domain that governs a
consequential action must independently answer *did the intended result actually
occur, and did anything else break* — payroll reconciliation, AWS-IAM residual
access, K8s RBAC residual, etc. This module is the single primitive those domains
converge on: express the answer as a set of expected-vs-actual **OutcomeCheck**s
and let `verify_outcome` classify the canonical `Outcome`.

Pure, dependency-free. The domain builds the checks (they carry the domain truth);
this module only classifies and never invents a passing result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .contract import Outcome


@dataclass
class OutcomeCheck:
    """One independent expected-vs-actual assertion about the mission's result."""
    name: str
    satisfied: bool
    detail: str = ""
    critical: bool = True        # a failed critical check => failed; non-critical => partial


def verify_outcome(checks: List[OutcomeCheck], *, method: str = "") -> Outcome:
    """Classify the mission outcome from independent checks (never a silent pass):
      * no checks            -> unknown  (we cannot say; honest, not "safe")
      * all satisfied        -> verified
      * any CRITICAL failure -> failed
      * only non-critical    -> partial
    `unintended[]` lists the failed checks so the proof records what actually broke.
    """
    if not checks:
        return Outcome(status="unknown", verification_method=method, unintended=[])
    failed = [c for c in checks if not c.satisfied]
    unintended = [f"{c.name}: {c.detail}" for c in failed]
    if not failed:
        status = "verified"
    elif any(c.critical for c in failed):
        status = "failed"
    else:
        status = "partial"
    return Outcome(status=status, verification_method=method, unintended=unintended)


def succeeded(outcome: Outcome) -> bool:
    return outcome.status == "verified"
