"""AI Org Graph.

Builds nodes + edges for an interactive org chart with calm hierarchical
layout. Each node carries the metrics we want to overlay:
  - attrition risk (low/medium/high)
  - succession readiness (none/groom/ready)
  - hiring hotspots (open reqs in this team)
  - manager span / load

The layout is deterministic so the UI doesn't shift between renders.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Employee
from app.services.attrition_service import AttritionFeatures, predict_batch
from app.services.org_design_service import _demo_employees as _demo_org  # type: ignore


# Demo metric overlays. In production this comes from real reviews/comp/risk.
_RISK_OVERLAY = {
    "Avery Chen": "high",
    "Jordan Patel": "medium",
    "Riley Singh": "medium",
}
# Fallback only. The live succession map now comes from calibration_service
# (real 9-box placements); see _succession_overlay_for below.
_SUCCESSION_OVERLAY = {
    "Avery Chen": "ready",
    "Emily Stone": "groom",
}


def _succession_overlay_for(org_id: str) -> dict[str, str]:
    """Live name -> succession status from the org's calibrated 9-box placements,
    falling back to the demo overlay when nothing has been calibrated yet."""
    try:
        from app.services.calibration_service import succession_overlay
        real = succession_overlay(org_id)
        if real:
            return real
    except Exception:
        pass
    return _SUCCESSION_OVERLAY
_HIRING_OVERLAY = {
    "Engineering": 2,
    "Sales": 1,
    "Design": 1,
    "Customer Success": 1,
}


@dataclass
class GraphNode:
    id: str
    name: str
    title: Optional[str]
    department: Optional[str]
    manager_id: Optional[str]
    depth: int
    x: int
    y: int
    span: int
    is_manager: bool
    attrition_band: str = "low"          # low | medium | high
    succession: str = "none"             # none | groom | ready
    hiring_reqs: int = 0
    # True when this node came from the invented fallback org rather than the
    # organisation's own employees. An org chart is read as a statement of who
    # reports to whom, and these nodes additionally carry an attrition band and
    # a succession rating -- claims about named people who do not exist.
    is_sample: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str = "reports_to"

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
def _layout(nodes: list[GraphNode]) -> None:
    """Simple deterministic horizontal-by-depth layout.

    For each depth band we evenly space nodes horizontally. Coordinates are
    integer pixels (the frontend translates them with a viewBox).
    """
    by_depth: dict[int, list[GraphNode]] = {}
    for n in nodes:
        by_depth.setdefault(n.depth, []).append(n)

    width = 1200
    layer_height = 120
    for depth, layer in by_depth.items():
        # stable order by name
        layer.sort(key=lambda x: x.name)
        gap = width // (len(layer) + 1)
        for idx, n in enumerate(layer, start=1):
            n.x = gap * idx
            n.y = 80 + depth * layer_height


def _node_from(row, depth: int, span: int, attrition: dict[str, str],
               succession: Optional[dict[str, str]] = None) -> GraphNode:
    """Accepts either an ORM Employee or a seed dict."""
    succession = succession if succession is not None else _SUCCESSION_OVERLAY
    if isinstance(row, dict):
        rid = row.get("id") or ""
        name = row.get("legal_name") or "—"
        title = row.get("job_title")
        dept = row.get("department")
        mgr = row.get("manager_employee_id")
    else:
        rid = str(getattr(row, "id", ""))
        name = getattr(row, "legal_name", "—")
        title = getattr(row, "job_title", None)
        dept = getattr(row, "department", None)
        mgr_attr = getattr(row, "manager_employee_id", None)
        mgr = str(mgr_attr) if mgr_attr else None

    return GraphNode(
        id=str(rid),
        name=name,
        title=title,
        department=dept,
        manager_id=(str(mgr) if mgr else None),
        depth=depth,
        x=0,
        y=0,
        span=span,
        is_manager=span > 0,
        attrition_band=attrition.get(name, "low"),
        succession=succession.get(name, "none"),
        hiring_reqs=_HIRING_OVERLAY.get(dept or "", 0) if (span > 0 or (title or "").lower().__contains__("vp")) else 0,
        # _demo_org() marks its people; a real Employee row has no such key.
        is_sample=bool(row.get("is_sample")) if isinstance(row, dict) else False,
    )


async def _fetch_employees(db: AsyncSession, org_id: str) -> list:
    try:
        from uuid import UUID as _UUID
        org_uuid = _UUID(org_id)
        res = await db.execute(select(Employee).where(Employee.org_id == org_uuid))
        rows = res.scalars().all()
        if rows:
            return list(rows)
    except Exception:
        pass
    return _demo_org()


async def build_graph(db: AsyncSession, org_id: str) -> dict:
    employees = await _fetch_employees(db, org_id)

    # Compute attrition overlay from the model + manual overrides
    preds = predict_batch([
        AttritionFeatures("e1", "Avery Chen",   department="Engineering",     tenure_years=2.4, months_since_last_raise=22, months_since_last_promotion=30, performance_rating=4.5, engagement_score=0.42, compa_ratio=0.82, overtime_hours_last_30d=38),
        AttritionFeatures("e2", "Jordan Patel", department="Sales",           tenure_years=1.8, months_since_last_raise=14, months_since_last_promotion=20, performance_rating=3.2, engagement_score=0.61, compa_ratio=0.97, pto_balance_days=22),
        AttritionFeatures("e5", "Riley Singh",  department="Design",          tenure_years=2.0, months_since_last_raise=18, months_since_last_promotion=24, performance_rating=4.8, compa_ratio=0.88, role_change_in_last_180d=True, pto_balance_days=19),
        AttritionFeatures("e6", "Emily Stone",  department="Customer Success",tenure_years=1.8, performance_rating=4.6, compa_ratio=0.94, engagement_score=0.71),
    ])
    attrition_map = {p.name: p.band for p in preds}
    attrition_map.update(_RISK_OVERLAY)

    # Live succession overlay from the org's calibrated 9-box placements.
    succession_map = _succession_overlay_for(org_id)

    # First pass: compute span counts by manager_id
    span_counts: dict[Optional[str], int] = {}
    for e in employees:
        mgr = e.get("manager_employee_id") if isinstance(e, dict) else getattr(e, "manager_employee_id", None)
        mgr = str(mgr) if mgr else None
        span_counts[mgr] = span_counts.get(mgr, 0) + 1

    # Compute depth by walking from each node up the chain
    by_id_attr = {(e.get("id") if isinstance(e, dict) else str(getattr(e, "id"))): e for e in employees}

    def depth(eid: str, seen: set[str]) -> int:
        e = by_id_attr.get(eid)
        if not e or eid in seen:
            return 0
        seen.add(eid)
        mgr = e.get("manager_employee_id") if isinstance(e, dict) else getattr(e, "manager_employee_id", None)
        mgr = str(mgr) if mgr else None
        if not mgr or mgr not in by_id_attr:
            return 0
        return 1 + depth(mgr, seen)

    nodes: list[GraphNode] = []
    for e in employees:
        eid = e.get("id") if isinstance(e, dict) else str(getattr(e, "id"))
        nodes.append(_node_from(e, depth=depth(eid, set()), span=span_counts.get(eid, 0),
                                attrition=attrition_map, succession=succession_map))

    _layout(nodes)

    edges: list[GraphEdge] = []
    for n in nodes:
        if n.manager_id and n.manager_id in by_id_attr:
            edges.append(GraphEdge(source=n.manager_id, target=n.id))

    # Summaries for the side rail
    departments = sorted({n.department for n in nodes if n.department})
    high_risk = [n for n in nodes if n.attrition_band == "high"]
    ready = [n for n in nodes if n.succession == "ready"]
    overloaded = [n for n in nodes if n.span >= 8]
    hotspots = sorted(
        ({"department": d, "open_reqs": _HIRING_OVERLAY.get(d, 0)} for d in departments if _HIRING_OVERLAY.get(d, 0)),
        key=lambda x: -x["open_reqs"],
    )

    return {
        "nodes": [n.to_dict() for n in nodes],
        "edges": [e.to_dict() for e in edges],
        "viewbox": {"width": 1200, "height": 80 + (max((n.depth for n in nodes), default=0) + 1) * 120 + 40},
        "departments": departments,
        "summary": {
            "total_nodes": len(nodes),
            "managers": sum(1 for n in nodes if n.is_manager),
            "max_depth": max((n.depth for n in nodes), default=0),
            "high_risk": [n.to_dict() for n in high_risk],
            "ready_successors": [n.to_dict() for n in ready],
            "overloaded_managers": [n.to_dict() for n in overloaded],
            "hiring_hotspots": hotspots,
        },
    }
