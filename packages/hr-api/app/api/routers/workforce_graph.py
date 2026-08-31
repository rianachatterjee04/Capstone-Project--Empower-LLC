"""Workforce Intelligence router.

The operating system for the ENTIRE workforce — humans + AI agents +
contractors + bots — in one graph, priced against one P&L, each node carrying a
trust score. Extends the existing org-graph / workforce-finance surfaces.

Endpoints (mounted under /api):
  GET  /workforce/graph              the living map (nodes + edges; filterable)
  GET  /workforce/node/{id}          full drill-in panel for one node
  GET  /workforce/summary            headcount-by-type + total cost + avg trust
  GET  /workforce/finance/roi        revenue-contribution / cost, ranked
  POST /workforce/finance/simulate   4 deterministic what-if scenarios
  GET  /workforce/intelligence       the exec headline (thin aggregate)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services import workforce_graph_service as wf
from app.services import workforce_finance_service as fin


router = APIRouter(prefix="/workforce", tags=["workforce-intelligence"])

_ROLES = ("owner", "admin", "hr", "manager")


def _allowed(actor: Actor) -> bool:
    return actor.role in _ROLES


# ---------------------------------------------------------------------------
# WORKFORCE GRAPH
# ---------------------------------------------------------------------------
@router.get("/graph")
async def graph(
    type: str | None = None,
    team: str | None = None,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    node_type = type if type in ("human", "ai_agent", "contractor", "bot") else None
    return await wf.build_graph(db, actor.org_id, node_type=node_type, team=team)


@router.get("/node/{node_id}")
async def node(
    node_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    detail = await wf.node_detail(db, actor.org_id, node_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Workforce node not found")
    return detail


@router.get("/summary")
async def summary(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await wf.summary(db, actor.org_id)


# ---------------------------------------------------------------------------
# WORKFORCE FINANCIAL INTELLIGENCE
# ---------------------------------------------------------------------------
@router.get("/finance/roi")
async def finance_roi(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return await fin.roi(db, actor.org_id)


@router.post("/finance/simulate")
async def finance_simulate(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        return await fin.simulate(db, actor.org_id, payload or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# WORKFORCE INTELLIGENCE HUB — the exec headline
# ---------------------------------------------------------------------------
@router.get("/intelligence")
async def intelligence(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    graph_summary = await wf.summary(db, actor.org_id)
    roi_data = await fin.roi(db, actor.org_id)

    # Top attrition risks straight off the graph's human nodes.
    full = await wf.build_graph(db, actor.org_id)
    human_risks = sorted(
        [n for n in full["nodes"] if n["type"] == "human"],
        key=lambda n: -n["risk_score"],
    )[:5]

    return {
        "as_of": graph_summary["as_of"],
        "headline": (
            f"{graph_summary['total_workforce']} workers "
            f"({graph_summary['human_count']} human · {graph_summary['ai_agent_count']} AI agents · "
            f"{graph_summary['bot_count']} bots · {graph_summary['contractor_count']} contractors) · "
            f"${graph_summary['total_workforce_cost']:,} total cost · avg trust {graph_summary['avg_trust']}"
        ),
        "workforce": {
            "headcount_by_type": graph_summary["headcount_by_type"],
            "total_workforce_cost": graph_summary["total_workforce_cost"],
            "avg_trust": graph_summary["avg_trust"],
            "avg_trust_ai": graph_summary["avg_trust_ai"],
        },
        "ai_agents": {
            "count": graph_summary["ai_agent_count"] + graph_summary["bot_count"],
            "avg_trust": graph_summary["avg_trust_ai"],
        },
        "top_roi_teams": roi_data["top_teams"],
        "top_roi_employees": roi_data["top_employees"],
        "org_roi_ratio": roi_data["org_roi_ratio"],
        "top_attrition_risks": [
            {"id": n["id"], "name": n["name"], "team": n["team"],
             "risk_score": n["risk_score"], "band": n["performance"].get("attrition_band")}
            for n in human_risks
        ],
    }
