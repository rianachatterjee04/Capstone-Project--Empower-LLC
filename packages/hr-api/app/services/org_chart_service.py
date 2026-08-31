"""Org-chart tree building + headcount/attrition math — pure functions.

Input rows are dicts with at least {id, manager_id}; extra keys (name,
job_title, department, ...) are carried through onto the node. Cycle-safe:
any employee whose manager chain loops (or whose manager id is unknown)
is promoted to a root rather than dropped.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def build_tree(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Nested org tree. Returns a list of root nodes, each
    {**row, "reports": [children...], "team_size": n} where team_size counts
    all transitive reports (self excluded)."""
    nodes: dict[str, dict] = {}
    for r in rows:
        node = dict(r)
        node["reports"] = []
        nodes[str(r["id"])] = node

    roots: list[dict] = []
    for node in nodes.values():
        mid = node.get("manager_id")
        mid = str(mid) if mid else None
        if not mid or mid not in nodes or mid == str(node["id"]):
            roots.append(node)
            continue
        # cycle guard: walk up; if we come back to ourselves, treat as root
        seen = {str(node["id"])}
        cur = mid
        cyclic = False
        while cur:
            if cur in seen:
                cyclic = True
                break
            seen.add(cur)
            parent = nodes.get(cur)
            nxt = parent.get("manager_id") if parent else None
            cur = str(nxt) if nxt else None
            if cur is not None and cur not in nodes:
                cur = None
        if cyclic:
            roots.append(node)
        else:
            nodes[mid]["reports"].append(node)

    def _count(node: dict) -> int:
        n = 0
        for child in node["reports"]:
            n += 1 + _count(child)
        node["team_size"] = n
        return n

    for root in roots:
        _count(root)

    roots.sort(key=lambda n: (-n["team_size"], str(n.get("name") or "")))
    return roots


def headcount_by_department(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """[{department, count}] sorted by count desc. Empty/missing department
    buckets as 'Unassigned'."""
    counts: dict[str, int] = {}
    for r in rows:
        dept = (r.get("department") or "").strip() or "Unassigned"
        counts[dept] = counts.get(dept, 0) + 1
    return [
        {"department": d, "count": c}
        for d, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def attrition_rate(terminations: int, headcount_start: int, headcount_end: int) -> float:
    """Annualized-style attrition metric: terminations / average headcount.
    Returns a fraction (0.10 = 10%). 0.0 when average headcount is 0."""
    avg = (max(0, headcount_start) + max(0, headcount_end)) / 2.0
    if avg <= 0:
        return 0.0
    return round(terminations / avg, 4)
