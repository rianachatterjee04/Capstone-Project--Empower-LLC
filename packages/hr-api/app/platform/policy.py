from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple
import uuid

Severity = Literal["low", "medium", "high", "critical"]

@dataclass
class PolicyVersion:
    policy_id: str
    version: int
    name: str
    created_at: datetime
    approved_by: str
    rules: List[Dict[str, Any]]  # simple JSON rules

@dataclass
class PolicyViolation:
    violation_id: str
    policy_id: str
    version: int
    severity: Severity
    message: str
    object_type: str
    object_id: str
    context: Dict[str, Any]

class PolicyEngine:
    """Lightweight policy engine with versioning + simulations.

    Rule format (simple but effective):
    {
      "if": {"field": "Shares", "op": ">", "value": 500000},
      "then": {"severity":"high", "message":"Grant exceeds 500k shares", "object_type":"grant"}
    }
    """

    def __init__(self) -> None:
        self._policies: Dict[str, List[PolicyVersion]] = {}

    def publish(self, name: str, rules: List[Dict[str, Any]], approved_by: str) -> PolicyVersion:
        policy_id = uuid.uuid4().hex
        pv = PolicyVersion(policy_id=policy_id, version=1, name=name, created_at=datetime.utcnow(), approved_by=approved_by, rules=rules)
        self._policies[policy_id] = [pv]
        return pv

    def supersede(self, policy_id: str, rules: List[Dict[str, Any]], approved_by: str) -> PolicyVersion:
        versions = self._policies.get(policy_id, [])
        if not versions:
            raise ValueError("unknown policy_id")
        newv = PolicyVersion(policy_id=policy_id, version=versions[-1].version+1, name=versions[-1].name,
                             created_at=datetime.utcnow(), approved_by=approved_by, rules=rules)
        versions.append(newv)
        return newv

    def latest(self, policy_id: str) -> PolicyVersion:
        versions = self._policies.get(policy_id, [])
        if not versions:
            raise ValueError("unknown policy_id")
        return versions[-1]

    def list_policies(self) -> List[PolicyVersion]:
        out=[]
        for vs in self._policies.values():
            out.append(vs[-1])
        return out

    def evaluate(self, policy: PolicyVersion, obj: Dict[str, Any], object_type: str, object_id: str) -> List[PolicyViolation]:
        violations: List[PolicyViolation] = []
        for r in policy.rules:
            cond = r.get("if", {})
            then = r.get("then", {})
            field = cond.get("field")
            op = cond.get("op")
            value = cond.get("value")
            if field is None or op is None:
                continue
            actual = obj.get(field)
            ok = _compare(actual, op, value)
            if ok:
                violations.append(PolicyViolation(
                    violation_id=uuid.uuid4().hex,
                    policy_id=policy.policy_id,
                    version=policy.version,
                    severity=then.get("severity","medium"),
                    message=then.get("message","Policy violation"),
                    object_type=object_type,
                    object_id=object_id,
                    context={"field": field, "actual": actual, "expected": value, "op": op},
                ))
        return violations

def _compare(actual: Any, op: str, value: Any) -> bool:
    try:
        if op == ">": return actual is not None and actual > value
        if op == "<": return actual is not None and actual < value
        if op == ">=": return actual is not None and actual >= value
        if op == "<=": return actual is not None and actual <= value
        if op == "==": return actual == value
        if op == "!=": return actual != value
        if op == "in": return actual in value
        if op == "not_in": return actual not in value
    except Exception:
        return False
    return False
