from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import re

# Minimal Policy DSL:
# {
#   "rules":[
#     {"when":{"entity":"case","severity_gte":"high","category_in":["harassment"]},
#      "then":{"sla_minutes":2880,"route":["manager","hr","legal","exec"]}}
#   ]
# }

@dataclass
class ParsedPolicy:
    name: str
    body: str
    dsl: Dict[str, Any]

def english_to_dsl(name: str, body: str) -> ParsedPolicy:
    """Heuristic parser: converts common HR policy sentences into executable DSL.
    Replace with LLM-based compiler later. Deterministic and safe for now.
    """
    rules: List[Dict[str, Any]] = []

    # Detect SLA like "within 48 hours" and category like harassment
    m = re.search(r"within\s+(\d+)\s*(hours|hour|days|day|minutes|minute)", body, re.I)
    sla_minutes = None
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("hour"):
            sla_minutes = n * 60
        elif unit.startswith("day"):
            sla_minutes = n * 24 * 60
        else:
            sla_minutes = n

    category = "harassment" if re.search(r"harass", body, re.I) else None
    severity_floor = "high" if re.search(r"high|critical", body, re.I) else None

    if sla_minutes and (category or severity_floor):
        when = {"entity": "case"}
        if category:
            when["category_in"] = [category]
        if severity_floor:
            when["severity_gte"] = severity_floor
        then = {"sla_minutes": sla_minutes, "route": ["manager","hr","legal","exec"]}
        rules.append({"when": when, "then": then})

    dsl = {"rules": rules, "version": 1, "compiler": "heuristic-v1"}
    return ParsedPolicy(name=name, body=body, dsl=dsl)

def severity_rank(s: str) -> int:
    order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return order.get((s or "").lower(), 0)

def rule_matches(rule_when: Dict[str, Any], entity: Dict[str, Any]) -> bool:
    if rule_when.get("entity") and rule_when["entity"] != entity.get("entity"):
        return False
    if "category_in" in rule_when:
        if (entity.get("category") or "").lower() not in [c.lower() for c in rule_when["category_in"]]:
            return False
    if "severity_gte" in rule_when:
        if severity_rank(entity.get("severity")) < severity_rank(rule_when["severity_gte"]):
            return False
    return True
