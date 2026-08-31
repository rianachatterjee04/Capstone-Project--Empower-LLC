"""Golden-vector tests for Workforce Intelligence.

Covers the two things only Fintra can build — the Workforce Graph (humans + AI
agents + contractors + bots in one map, each with a trust score) and Workforce
Financial Intelligence (ROI + the 4-scenario simulator).

DB-free: the graph/finance math is deterministic in-process, so the vectors are
exercised directly with hand-checked numbers. A handful of TestClient cases
drive the routers end-to-end with ``require_org`` + ``db_session`` overridden so
role gating and the HTTP contract are proven without a DB or a live LLM.

Run:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_workforce_intelligence.py -q
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Actor, db_session, require_org
from app.main import app
from app.services import workforce_graph_service as wf
from app.services import workforce_finance_service as fin


BENEFITS = fin.BENEFITS_LOADING_RATE  # 0.28


def _run(coro):
    """Run a coroutine on a fresh event loop.

    Using a dedicated loop (rather than the ambient one) keeps these sync tests
    robust when other test modules close / swap the default loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ===========================================================================
# WORKFORCE GRAPH — the map
# ===========================================================================
def test_1_graph_builds_all_node_types():
    b = wf.build_workforce()
    types = {}
    for n in b["nodes"]:
        types[n.type] = types.get(n.type, 0) + 1
    # human + ai_agent + contractor + bot must ALL be present in one graph.
    assert types["human"] >= 1
    assert types["ai_agent"] >= 1
    assert types["contractor"] >= 1
    assert types["bot"] >= 1
    assert types == {"human": 12, "ai_agent": 6, "bot": 2, "contractor": 2}


def test_2_graph_has_edges_and_no_dangling():
    b = wf.build_workforce()
    ids = {n.id for n in b["nodes"]}
    assert len(b["edges"]) == 21
    for e in b["edges"]:
        assert e["source"] in ids and e["target"] in ids
        assert e["kind"] == "reports_to"


def test_3_every_node_carries_trust_and_risk():
    b = wf.build_workforce()
    for n in b["nodes"]:
        assert isinstance(n.trust_score, int) and 0 <= n.trust_score <= 100
        assert isinstance(n.risk_score, int) and 0 <= n.risk_score <= 100
        assert n.role and n.team is not None
        assert "kind" in n.compensation


def test_4_human_trust_and_risk_are_attrition_derived():
    b = wf.build_workforce()
    avery = next(n for n in b["nodes"] if n.id == "e1")
    # Avery Chen is the canonical flight risk (high band, risk 80).
    assert avery.performance["attrition_band"] == "high"
    assert avery.risk_score == 80
    # trust = 70 + (4.5-3)*10 - 0.25*80 = 65
    assert avery.trust_score == 65


def test_5_ai_agent_trust_score_formula():
    # ag_payroll: granted 20, rejected 0 -> rate 1.0; pending 2; incidents 0.
    # trust = 50 + 45*1.0 - 10*0 - 3*2 = 89
    payroll = next(a for a in wf._ai_agent_seed() if a["id"] == "ag_payroll")
    assert wf.agent_trust_score(payroll) == 89


def test_6_ai_agent_risk_reflects_scope_sensitivity_and_autonomy():
    payroll = next(a for a in wf._ai_agent_seed() if a["id"] == "ag_payroll")
    trust = wf.agent_trust_score(payroll)  # 89
    # sensitive scopes: payroll.write, payroll.run, funds.move -> 3; autonomy approve -> +6
    # risk = (100-89) + 4*3 + 6 = 29
    assert wf.agent_risk_score(payroll, trust) == 29


def test_7_bot_incidents_reduce_trust():
    b = wf.build_workforce()
    notifier = next(n for n in b["nodes"] if n.id == "bot_notifier")  # 0 incidents
    atssync = next(n for n in b["nodes"] if n.id == "bot_atssync")    # 2 incidents
    # notifier: 50+45 = 95 ; atssync: 50+45 - 10*2 = 75
    assert notifier.trust_score == 95
    assert atssync.trust_score == 75
    assert atssync.trust_score < notifier.trust_score


def test_8_contractor_scored_and_priced():
    b = wf.build_workforce()
    dana = next(n for n in b["nodes"] if n.id == "c1")
    assert dana.type == "contractor"
    # annual cost = 95 * 30 * 52 = 148,200
    assert dana.compensation["annual_cost"] == 95 * 30 * 52
    assert 30 <= dana.trust_score <= 95


def test_9_node_types_have_correct_cost_kind():
    b = wf.build_workforce()
    by_id = {n.id: n for n in b["nodes"]}
    assert by_id["e1"].compensation["kind"] == "salary"
    assert by_id["ag_payroll"].compensation["kind"] == "run_cost"
    assert by_id["c1"].compensation["kind"] == "contract"


# ===========================================================================
# SUMMARY — headcount by type + total cost + avg trust
# ===========================================================================
def test_10_summary_headcount_by_type():
    s = wf._summary_from(wf.build_workforce()["nodes"])
    assert s["headcount_by_type"] == {"human": 12, "ai_agent": 6, "bot": 2, "contractor": 2}
    assert s["total_workforce"] == 22
    assert s["human_count"] == 12 and s["ai_agent_count"] == 6


def test_11_summary_total_cost_and_avg_trust():
    nodes = wf.build_workforce()["nodes"]
    s = wf._summary_from(nodes)
    assert s["total_workforce_cost"] == round(sum(n.cost_annual for n in nodes))
    # human cash cost is benefits-loaded.
    assert s["cost_by_type"]["human"] == round(sum(
        n.compensation["annual_base"] * (1 + BENEFITS) for n in nodes if n.type == "human"))
    assert 0 <= s["avg_trust"] <= 100
    assert s["avg_trust"] == round(sum(n.trust_score for n in nodes) / len(nodes), 1)


# ===========================================================================
# ROI — revenue-contribution / cost
# ===========================================================================
def test_12_roi_ranks_teams_by_revenue_over_cost():
    data = _run(fin.roi(None, "o"))
    teams = data["teams"]
    # sorted descending by roi_ratio
    ratios = [t["roi_ratio"] for t in teams]
    assert ratios == sorted(ratios, reverse=True)
    # HR / Executive are cost centers (0 revenue -> roi 0, flagged)
    hr = next(t for t in teams if t["team"] == "HR")
    assert hr["is_cost_center"] is True and hr["roi_ratio"] == 0.0


def test_13_roi_worked_example_engineering():
    data = _run(fin.roi(None, "o"))
    eng = next(t for t in data["teams"] if t["team"] == "Engineering")
    # Eng base in EMPLOYEE_COMP: 165+195+175+185+155 = 875k ; loaded *1.28 = 1,120,000
    assert eng["annual_cost_loaded"] == round(875_000 * (1 + BENEFITS))
    assert eng["revenue_attributed"] == 6_000_000
    # roi = 6,000,000 / 1,120,000 = 5.36
    assert eng["roi_ratio"] == round(6_000_000 / round(875_000 * (1 + BENEFITS)), 2)


# ===========================================================================
# SIMULATOR — 4 deterministic scenarios
# ===========================================================================
def test_14_simulate_commission_change():
    out = fin._simulate_commission_change(2, "o")
    # +2pt on $4.2M Sales revenue -> 84k base ; loaded 107,520 ; EBITDA -107,520
    assert out["payroll_base_delta"] == 84_000
    assert out["payroll_loaded_delta"] == round(84_000 * (1 + BENEFITS)) == 107_520
    assert out["ebitda_delta"] == -107_520
    assert out["narrative"]["source"] in ("fallback", "ai")


def test_15_simulate_headcount_add_cost_and_when():
    out = fin._simulate_headcount_add("Engineering", 2, "o")
    # avg Eng base 175k * 2 = 350k ; loaded 448,000
    assert out["avg_base_per_hire"] == 175_000
    assert out["added_cost_loaded"] == 448_000
    # revenue/head 1.2M -> monthly added 200k -> breakeven 448000/200000 = 2.2
    assert out["when_to_hire"]["months_to_breakeven"] == 2.2
    assert "pays back" in out["when_to_hire"]["verdict"]


def test_16_simulate_attrition_backfill_cost():
    out = fin._simulate_attrition("e8", "o")  # Sarah Chen, 185k, senior + Engineering
    b = out["backfill_breakdown"]
    assert b["recruiting"] == round(185_000 * 0.20) == 37_000
    assert b["ramp_loss"] == round(185_000 * 0.25) == 46_250
    assert b["vacancy_productivity"] == round(185_000 * (2 / 12)) == 30_833
    assert out["cost_to_backfill"] == 37_000 + 46_250 + 30_833
    assert out["knowledge_risk"] == "high"


def test_17_simulate_new_market_headcount_and_payroll():
    out = fin._simulate_new_market("Germany", "standard", "o")
    # standard plan -> 3 Sales, 1 HR, 1 Finance
    assert out["recommended_headcount"] == {"Sales": 3, "HR": 1, "Finance": 1}
    assert out["total_headcount"] == 5
    # base = 3*135k + 110k + 130k = 645k ; Germany factor 0.95 -> 612,750 ; loaded 784,320
    assert out["estimated_payroll_base"] == 645_000
    assert out["region_cost_factor"] == 0.95
    assert out["estimated_payroll_loaded"] == round(round(645_000 * 0.95) * (1 + BENEFITS)) == 784_320


def test_18_simulate_unknown_kind_raises():
    with pytest.raises(ValueError):
        _run(fin.simulate(None, "o", {"kind": "bogus"}))


# ===========================================================================
# FAIL-SOFT + ORG SCOPING
# ===========================================================================
class _BrokenDB:
    """A DB stand-in whose every call raises — proves the graph fails soft to
    the deterministic seed instead of 500ing when finance/HR data is absent."""
    async def execute(self, *a, **k):
        raise RuntimeError("db down")

    async def rollback(self):
        return None


def test_19_graph_failsoft_when_db_absent():
    out = _run(wf.build_graph(_BrokenDB(), str(uuid.uuid4())))
    types = {}
    for n in out["nodes"]:
        types[n["type"]] = types.get(n["type"], 0) + 1
    assert types["human"] == 12 and types["ai_agent"] == 6
    assert out["summary"]["total_workforce"] == 22


def test_20_attrition_failsoft_unknown_employee():
    # Unknown employee id -> org-median base, no crash.
    out = fin._simulate_attrition("does-not-exist", "o")
    assert out["cost_to_backfill"] > 0
    assert out["name"] == "does-not-exist"


def test_21_org_scoping_two_orgs_independent():
    a = _run(wf.summary(_BrokenDB(), "org-a"))
    b = _run(wf.summary(_BrokenDB(), "org-b"))
    # Deterministic canonical workforce per org; both well-formed + independent.
    assert a["total_workforce"] == b["total_workforce"] == 22
    assert a["as_of"] is not None and b["as_of"] is not None


# ===========================================================================
# HTTP contract — role gating + wiring (require_org + db_session overridden)
# ===========================================================================
ORG = "11111111-1111-1111-1111-111111111111"
UID = "22222222-2222-2222-2222-222222222222"


def _client(role: str) -> TestClient:
    app.dependency_overrides[require_org] = lambda: Actor(
        user_id=UID, org_id=ORG, role=role, claims={"email": "x@y.z"})
    app.dependency_overrides[db_session] = lambda: _BrokenDB()
    return TestClient(app)


def _reset():
    app.dependency_overrides.pop(require_org, None)
    app.dependency_overrides.pop(db_session, None)


def test_22_http_graph_and_node_and_summary():
    c = _client("owner")
    try:
        g = c.get("/api/workforce/graph")
        assert g.status_code == 200
        body = g.json()
        assert body["summary"]["ai_agent_count"] == 6
        # drill-in on an AI agent
        n = c.get("/api/workforce/node/ag_payroll")
        assert n.status_code == 200 and n.json()["node"]["trust_score"] == 89
        # 404 on unknown
        assert c.get("/api/workforce/node/nope").status_code == 404
        s = c.get("/api/workforce/summary")
        assert s.status_code == 200 and s.json()["total_workforce"] == 22
    finally:
        _reset()


def test_23_http_graph_type_filter():
    c = _client("hr")
    try:
        g = c.get("/api/workforce/graph?type=ai_agent")
        assert g.status_code == 200
        assert all(n["type"] == "ai_agent" for n in g.json()["nodes"])
    finally:
        _reset()


def test_24_http_finance_roi_and_simulate():
    c = _client("admin")
    try:
        roi = c.get("/api/workforce/finance/roi")
        assert roi.status_code == 200 and roi.json()["org_roi_ratio"] > 0
        sim = c.post("/api/workforce/finance/simulate", json={"kind": "commission_change", "pct": 2})
        assert sim.status_code == 200 and sim.json()["ebitda_delta"] == -107_520
        bad = c.post("/api/workforce/finance/simulate", json={"kind": "bogus"})
        assert bad.status_code == 400
    finally:
        _reset()


def test_25_http_intelligence_hub():
    c = _client("owner")
    try:
        r = c.get("/api/workforce/intelligence")
        assert r.status_code == 200
        body = r.json()
        assert "headline" in body
        assert body["ai_agents"]["count"] == 8  # 6 agents + 2 bots
        assert len(body["top_attrition_risks"]) >= 1
        assert body["top_attrition_risks"][0]["risk_score"] >= body["top_attrition_risks"][-1]["risk_score"]
    finally:
        _reset()


def test_26_http_role_gating():
    c = _client("employee")
    try:
        assert c.get("/api/workforce/graph").status_code == 403
        assert c.get("/api/workforce/finance/roi").status_code == 403
        assert c.get("/api/workforce/intelligence").status_code == 403
    finally:
        _reset()
