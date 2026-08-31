"""Golden-vector tests for the three Lattice-parity gap closers:

  1) 1:1s              (app.services.oneonone_service + /one-on-ones router)
  2) Engagement / eNPS (app.services.engagement_service + /engagement router)
  3) Grow / ladders    (app.services.grow_service + /grow router)

DB-free: the services are pure in-process stores, so the math / privacy /
k-anonymity logic is exercised directly with hand-checked vectors. A handful of
TestClient cases drive the routers end-to-end with ``require_org`` overridden so
private-note filtering and role gating are proven at the HTTP boundary — no DB,
no live LLM.

Run:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_hr_habit_grow.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Actor, require_org
from app.main import app
from app.services import oneonone_service as one
from app.services import engagement_service as eng
from app.services import grow_service as grow


# ---------------------------------------------------------------------------
# helpers — give every test a clean, un-seeded org
# ---------------------------------------------------------------------------
def _fresh_one() -> str:
    org = str(uuid.uuid4())
    one._seeded.add(org)
    one._store[org] = []
    return org


def _fresh_eng() -> str:
    org = str(uuid.uuid4())
    eng._seeded.add(org)
    eng._store[org] = []
    return org


def _fresh_grow() -> str:
    org = str(uuid.uuid4())
    grow._seeded.add(org)
    grow._ladders[org] = []
    grow._plans[org] = []
    return org


MANAGER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REPORT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OUTSIDER = "cccccccc-cccc-cccc-cccc-cccccccccccc"


# ===========================================================================
# 1:1s
# ===========================================================================
def test_1_series_create_and_list():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT, "cadence": "weekly"})
    assert s and s["cadence"] == "weekly" and s["next_date"]
    listing = one.list_series(org, MANAGER, "manager")
    assert listing["total"] == 1


def test_2_meeting_create_and_status():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT})
    m = one.create_meeting(org, s["id"], {"date": "2026-07-10"})
    assert m["status"] == "scheduled"
    done = one.set_meeting_status(org, m["id"], "done")
    assert done["status"] == "done"
    assert one.set_meeting_status(org, m["id"], "bogus") is None


def test_3_agenda_and_action_crud():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT})
    m = one.create_meeting(org, s["id"], {})
    a = one.add_agenda_item(org, m["id"], "Roadmap context", MANAGER, "manager")
    assert a and a["checked"] is False
    upd = one.update_agenda_item(org, a["id"], MANAGER, "manager", {"checked": True})
    assert upd["checked"] is True
    act = one.add_action_item(org, m["id"], "Send doc", assignee_user_id=MANAGER, due="2026-07-15")
    assert act and act["done"] is False
    assert one.set_action_done(org, act["id"], True)["done"] is True
    tp = one.add_talking_point(org, m["id"], "Growth to Senior", REPORT)
    assert tp["text"] == "Growth to Senior"


def test_4_private_note_hidden_from_report():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT})
    m = one.create_meeting(org, s["id"], {})
    one.add_agenda_item(org, m["id"], "shared item", MANAGER, "manager", is_private=False)
    one.add_agenda_item(org, m["id"], "MANAGER SECRET", MANAGER, "manager", is_private=True)
    # report's view must NOT contain the manager's private note
    as_report = one.get_meeting(org, m["id"], REPORT)
    texts = [x["text"] for x in as_report["agenda_items"]]
    assert "shared item" in texts
    assert "MANAGER SECRET" not in texts


def test_5_private_note_visible_to_author():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT})
    m = one.create_meeting(org, s["id"], {})
    one.add_agenda_item(org, m["id"], "MANAGER SECRET", MANAGER, "manager", is_private=True)
    one.add_agenda_item(org, m["id"], "REPORT SECRET", REPORT, "report", is_private=True)
    mgr_view = [x["text"] for x in one.get_meeting(org, m["id"], MANAGER)["agenda_items"]]
    rep_view = [x["text"] for x in one.get_meeting(org, m["id"], REPORT)["agenda_items"]]
    assert "MANAGER SECRET" in mgr_view and "REPORT SECRET" not in mgr_view
    assert "REPORT SECRET" in rep_view and "MANAGER SECRET" not in rep_view
    # viewer=None (safe default) hides ALL private items
    none_view = [x["text"] for x in one.get_meeting(org, m["id"], None)["agenda_items"]]
    assert none_view == []


def test_6_suggest_agenda_failsoft():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT})
    out = one.suggest_agenda(org, s["id"])
    # No live LLM in tests → deterministic fallback, always useful output.
    assert out["source"] in ("fallback", "ai")
    assert len(out["suggestions"]) >= 3


def test_7_oneonone_privacy_over_http():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT})
    m = one.create_meeting(org, s["id"], {})

    def as_manager():
        return Actor(user_id=MANAGER, org_id=org, role="manager", claims={})

    def as_report():
        return Actor(user_id=REPORT, org_id=org, role="employee", claims={})

    client = TestClient(app)
    # manager posts a private note
    app.dependency_overrides[require_org] = as_manager
    r = client.post(f"/api/one-on-ones/meetings/{m['id']}/agenda",
                    json={"text": "private to manager", "is_private": True})
    assert r.status_code == 200
    # manager sees it
    mv = client.get(f"/api/one-on-ones/meetings/{m['id']}").json()
    assert any(a["text"] == "private to manager" for a in mv["agenda_items"])
    # report does NOT see it
    app.dependency_overrides[require_org] = as_report
    rv = client.get(f"/api/one-on-ones/meetings/{m['id']}").json()
    assert all(a["text"] != "private to manager" for a in rv["agenda_items"])
    app.dependency_overrides.clear()


def test_8_oneonone_access_control_over_http():
    org = _fresh_one()
    s = one.create_series(org, {"manager_user_id": MANAGER, "report_user_id": REPORT})
    client = TestClient(app)
    app.dependency_overrides[require_org] = lambda: Actor(user_id=OUTSIDER, org_id=org, role="employee", claims={})
    r = client.get(f"/api/one-on-ones/series/{s['id']}/meetings")
    assert r.status_code == 403
    app.dependency_overrides.clear()


# ===========================================================================
# Engagement / eNPS
# ===========================================================================
def test_9_enps_math_worked_example():
    # scores: 10,9,9 (promoters=3) · 8,7 (passives=2) · 6,5 (detractors=2), n=7
    # eNPS = round((3-2)/7*100) = round(14.28) = 14
    block = eng.compute_enps([10, 9, 9, 8, 7, 6, 5])
    assert block["promoters"] == 3
    assert block["passives"] == 2
    assert block["detractors"] == 2
    assert block["enps"] == 14


def _build_survey(org, anonymous=True, audience=None):
    s = eng.create_survey(org, {"title": "Pulse", "type": "engagement",
                                "anonymous": anonymous, "audience_size": audience})
    sid = s["id"]
    q_enps = eng.add_question(org, sid, {"text": "recommend?", "kind": "enps_0_10"})
    q_lead = eng.add_question(org, sid, {"text": "feedback?", "kind": "scale_1_5", "category": "leadership"})
    q_grow = eng.add_question(org, sid, {"text": "grow?", "kind": "scale_1_5", "category": "growth"})
    q_open = eng.add_question(org, sid, {"text": "notes?", "kind": "open"})
    eng.set_status(org, sid, "open")
    return sid, q_enps["id"], q_lead["id"], q_grow["id"], q_open["id"]


def test_10_participation_rate():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=False, audience=5)
    for i in range(3):
        eng.submit_response(org, sid, f"u{i}", {qe: 9, ql: 4, qg: 4})
    res = eng.results(org, sid)
    # 3 unique respondents / audience 5 → 60%
    assert res["participation_rate"] == 60


def test_11_driver_averages_by_category():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=False, audience=None)
    eng.submit_response(org, sid, "u1", {ql: 5, qg: 5})
    eng.submit_response(org, sid, "u2", {ql: 4, qg: 3})
    eng.submit_response(org, sid, "u3", {ql: 3, qg: 1})
    res = eng.results(org, sid)
    drivers = {d["category"]: d for d in res["drivers"]}
    assert drivers["leadership"]["mean"] == 4.0     # (5+4+3)/3
    assert drivers["growth"]["mean"] == 3.0         # (5+3+1)/3


def test_12_driver_correlation_deterministic():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=False, audience=None)
    eng.submit_response(org, sid, "u1", {ql: 5, qg: 5})
    eng.submit_response(org, sid, "u2", {ql: 4, qg: 3})
    eng.submit_response(org, sid, "u3", {ql: 3, qg: 1})
    r1 = eng.results(org, sid)
    r2 = eng.results(org, sid)
    d1 = {d["category"]: d["correlation"] for d in r1["drivers"]}
    d2 = {d["category"]: d["correlation"] for d in r2["drivers"]}
    assert d1 == d2                                  # deterministic
    assert 0.0 <= d1["leadership"] <= 1.0            # moves with headline


def test_13_k_anonymity_suppresses_under_three():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=True, audience=10)
    eng.submit_response(org, sid, "u1", {qe: 9, ql: 5})
    eng.submit_response(org, sid, "u2", {qe: 8, ql: 4})   # only 2 responses
    res = eng.results(org, sid)
    assert res["suppressed"] is True
    assert res["overall_score"] is None
    assert res["enps"] is None
    assert res["drivers"] == []


def test_14_k_anonymity_visible_at_three():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=True, audience=10)
    eng.submit_response(org, sid, "u1", {qe: 9, ql: 5})
    eng.submit_response(org, sid, "u2", {qe: 8, ql: 4})
    eng.submit_response(org, sid, "u3", {qe: 6, ql: 3})   # now 3 → visible
    res = eng.results(org, sid)
    assert res["suppressed"] is False
    assert res["enps"] is not None
    lead = [d for d in res["drivers"] if d["category"] == "leadership"][0]
    assert lead["suppressed"] is False and lead["n"] == 3


def test_15_anonymity_no_individual_leak():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=True, audience=10)
    for i in range(3):
        eng.submit_response(org, sid, f"secret-user-{i}", {qe: 9, ql: 5})
    res = eng.results(org, sid)
    survey = eng.get_survey(org, sid)
    blob = repr(res) + repr(survey)
    # No respondent identity or raw per-person answers escape in the aggregate.
    assert "secret-user-" not in blob
    assert "respondent_user_id" not in blob
    assert "responses" not in survey        # metadata only


def test_16_submit_only_when_open():
    org = _fresh_eng()
    s = eng.create_survey(org, {"title": "Draft survey", "anonymous": True})
    q = eng.add_question(org, s["id"], {"text": "x", "kind": "scale_1_5", "category": "growth"})
    # still draft → rejected
    out = eng.submit_response(org, s["id"], "u1", {q["id"]: 4})
    assert out["error"] == "not_open"
    eng.set_status(org, s["id"], "open")
    assert eng.submit_response(org, s["id"], "u1", {q["id"]: 4})["submitted"] is True
    eng.set_status(org, s["id"], "closed")
    assert eng.submit_response(org, s["id"], "u2", {q["id"]: 4})["error"] == "not_open"


def test_17_open_submit_close_flow_and_insights_failsoft():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=False, audience=None)
    for i in range(3):
        eng.submit_response(org, sid, f"u{i}", {qe: 9, ql: 4, qg: 4, qo: "more growth please"})
    ins = eng.insights(org, sid)
    assert ins["source"] in ("fallback", "ai")
    assert isinstance(ins["summary"], str) and ins["summary"]


def test_18_engagement_role_gate_over_http():
    org = _fresh_eng()
    sid, qe, ql, qg, qo = _build_survey(org, anonymous=True, audience=10)
    client = TestClient(app)
    # an employee CAN submit
    app.dependency_overrides[require_org] = lambda: Actor(user_id="e1", org_id=org, role="employee", claims={})
    r = client.post(f"/api/engagement/surveys/{sid}/responses", json={"answers": {qe: 9, ql: 5}})
    assert r.status_code == 200
    # ...but an employee CANNOT read aggregate results
    rr = client.get(f"/api/engagement/surveys/{sid}/results")
    assert rr.status_code == 403
    app.dependency_overrides.clear()


# ===========================================================================
# Grow / career ladders
# ===========================================================================
def _build_ladder(org):
    lad = grow.create_ladder(org, {"family": "Engineering"})
    lid = lad["id"]
    l1 = grow.add_level(org, lid, {"name": "L1", "title": "Engineer", "index": 1})
    l2 = grow.add_level(org, lid, {"name": "L2", "title": "Senior Engineer", "index": 2})
    craft = grow.add_competency(org, lid, {"name": "Craft", "category": "craft"})
    collab = grow.add_competency(org, lid, {"name": "Collaboration", "category": "collab"})
    grow.set_expectation(org, lid, {"competency_id": craft["id"], "level_id": l2["id"],
                                    "rubric": "ships reliably", "expected_rating": 4})
    grow.set_expectation(org, lid, {"competency_id": collab["id"], "level_id": l2["id"],
                                    "rubric": "mentors", "expected_rating": 5})
    return lid, l1["id"], l2["id"], craft["id"], collab["id"]


def test_19_ladder_level_competency_expectation_crud():
    org = _fresh_grow()
    lid, l1, l2, craft, collab = _build_ladder(org)
    lad = grow.get_ladder(org, lid)
    assert len(lad["levels"]) == 2
    assert len(lad["competencies"]) == 2
    assert len(lad["expectations"]) == 2
    # upsert same (competency, level) → updates, does not duplicate
    grow.set_expectation(org, lid, {"competency_id": craft, "level_id": l2,
                                    "rubric": "ships reliably v2", "expected_rating": 3})
    lad2 = grow.get_ladder(org, lid)
    assert len(lad2["expectations"]) == 2
    craft_exp = [e for e in lad2["expectations"] if e["competency_id"] == craft][0]
    assert craft_exp["expected_rating"] == 3 and craft_exp["rubric"] == "ships reliably v2"


def test_20_growth_plan_gap_worked_example():
    org = _fresh_grow()
    lid, l1, l2, craft, collab = _build_ladder(org)
    plan = grow.create_plan(org, {"employee_id": "e-avery", "ladder_id": lid,
                                  "current_level_id": l1, "target_level_id": l2})
    grow.set_rating(org, plan["id"], {"competency_id": craft, "manager": 2, "self": 4})
    grow.set_rating(org, plan["id"], {"competency_id": collab, "manager": 5})
    gap = grow.gap_view(org, plan["id"])
    by = {r["competency_id"]: r for r in gap["competencies"]}
    # craft: expected 4 at L2, manager rating 2 → gap 2, below bar
    assert by[craft]["target_expected_rating"] == 4
    assert by[craft]["current_rating"] == 2       # manager wins over self
    assert by[craft]["gap"] == 2
    assert by[craft]["below_bar"] is True
    # collab: expected 5, manager 5 → gap 0, at bar
    assert by[collab]["gap"] == 0
    assert by[collab]["below_bar"] is False


def test_21_gap_below_bar_sorted_biggest_first():
    org = _fresh_grow()
    lid, l1, l2, craft, collab = _build_ladder(org)
    plan = grow.create_plan(org, {"employee_id": "e1", "ladder_id": lid,
                                  "current_level_id": l1, "target_level_id": l2})
    grow.set_rating(org, plan["id"], {"competency_id": craft, "manager": 3})   # gap 1
    grow.set_rating(org, plan["id"], {"competency_id": collab, "manager": 1})  # gap 4
    gap = grow.gap_view(org, plan["id"])
    assert gap["below_bar_count"] == 2
    assert gap["below_bar"][0]["competency_id"] == collab   # biggest gap first
    assert gap["below_bar"][0]["gap"] == 4


def test_22_tie_plan_to_goal_and_review():
    org = _fresh_grow()
    lid, l1, l2, craft, collab = _build_ladder(org)
    plan = grow.create_plan(org, {"employee_id": "e1", "ladder_id": lid,
                                  "current_level_id": l1, "target_level_id": l2})
    grow.link_plan(org, plan["id"], {"goal_id": "goal-123", "review_id": "rev-456"})
    got = grow.get_plan(org, plan["id"])
    assert got["linked_goal_id"] == "goal-123"
    assert got["linked_review_id"] == "rev-456"
    gap = grow.gap_view(org, plan["id"])
    assert gap["linked_goal_id"] == "goal-123"
    # growth goal linking to goals.py
    grow.add_growth_goal(org, plan["id"], {"text": "Lead migration", "goal_id": "goal-123"})
    assert grow.get_plan(org, plan["id"])["growth_goals"][-1]["goal_id"] == "goal-123"


def test_23_suggest_actions_failsoft():
    org = _fresh_grow()
    lid, l1, l2, craft, collab = _build_ladder(org)
    plan = grow.create_plan(org, {"employee_id": "e1", "ladder_id": lid,
                                  "current_level_id": l1, "target_level_id": l2})
    grow.set_rating(org, plan["id"], {"competency_id": craft, "manager": 1})
    out = grow.suggest_actions(org, plan["id"])
    assert out["source"] in ("fallback", "ai")
    assert len(out["actions"]) >= 1


def test_24_grow_role_gate_over_http():
    org = _fresh_grow()
    client = TestClient(app)
    # employee cannot create a ladder
    app.dependency_overrides[require_org] = lambda: Actor(user_id="e1", org_id=org, role="employee", claims={})
    r = client.post("/api/grow/ladders", json={"family": "Sales"})
    assert r.status_code == 403
    # hr can
    app.dependency_overrides[require_org] = lambda: Actor(user_id="h1", org_id=org, role="hr", claims={})
    r2 = client.post("/api/grow/ladders", json={"family": "Sales"})
    assert r2.status_code == 200 and r2.json()["family"] == "Sales"
    app.dependency_overrides.clear()
