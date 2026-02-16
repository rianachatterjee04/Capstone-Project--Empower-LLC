from __future__ import annotations
from typing import Any, Dict, List

# Very small DSL MVP (extendable):
# Lines like:
#   SLA: harassment_report.review <= 48h
#   ESCALATE: to=hr,legal when severity>=high
#   NOTIFY: to=exec when severity>=critical
#
# Output rules are JSON objects.

def parse_policy(text: str) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("sla:"):
            rhs = line.split(":",1)[1].strip()
            # e.g. harassment_report.review <= 48h
            parts = rhs.replace(" ", "").split("<=")
            if len(parts)==2 and parts[1].endswith("h"):
                rules.append({"type":"sla","metric":parts[0], "hours": int(parts[1][:-1])})
        elif line.lower().startswith("escalate:"):
            rhs = line.split(":",1)[1].strip()
            rules.append({"type":"escalate","raw": rhs})
        elif line.lower().startswith("notify:"):
            rhs = line.split(":",1)[1].strip()
            rules.append({"type":"notify","raw": rhs})
        else:
            rules.append({"type":"custom","raw": line})
    return rules

def dry_run(rules: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    # For demo: determine which rules would trigger given context
    out = []
    for r in rules:
        if r["type"] == "sla":
            out.append({"rule": r, "would_schedule": True})
        else:
            out.append({"rule": r, "would_schedule": False})
    return out
