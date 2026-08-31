"""Golden-vector tests for the three NET-NEW P0 HR differentiators.

  1) PAY EQUITY            (app.services.pay_equity_service + /pay-equity router)
  2) CANDIDATE INTEGRITY   (app.services.candidate_integrity_service + /candidate-integrity)
  3) EXPLAINABLE SCORING + HITL RECOURSE
                           (app.services.interview_score_review_service + /interviews/*)

DB-free: the services are pure / in-process, so the math, band thresholds,
fail-soft behaviour, audit trail and org-scoping are exercised directly with
hand-checked vectors. A handful of TestClient cases drive the routers end-to-end
with ``require_org`` overridden so role gating is proven at the HTTP boundary.

Run:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_hr_differentiators.py -q
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.deps import Actor, require_org
from app.main import app
from app.services import pay_equity_service as pe
from app.services import candidate_integrity_service as ci
from app.services import interview_score_review_service as sr
from app.services import interview_scorecard_service as sc


# ===========================================================================
# helpers
# ===========================================================================
def _fresh_pe_org() -> str:
    return str(uuid.uuid4())


def _worked_example() -> list[pe.PEEmployee]:
    """The hand-checked worked example (all Engineering, Remote, 2-5y band):
       L3: M 100k,100k | F 90k,94k ;  L4: M 140k,140k | F 130k.
       raw gap = 12.78%, adjusted (control level) = 7.65%, budget@5% = 9000."""
    E = pe.PEEmployee
    return [
        E(id="m1", name="M1", salary=100_000, gender="male", level="L3",
          job_family="Engineering", location="Remote", tenure_years=3),
        E(id="m2", name="M2", salary=100_000, gender="male", level="L3",
          job_family="Engineering", location="Remote", tenure_years=3),
        E(id="f1", name="F1", salary=90_000, gender="female", level="L3",
          job_family="Engineering", location="Remote", tenure_years=3),
        E(id="f2", name="F2", salary=94_000, gender="female", level="L3",
          job_family="Engineering", location="Remote", tenure_years=3),
        E(id="m3", name="M3", salary=140_000, gender="male", level="L4",
          job_family="Engineering", location="Remote", tenure_years=3),
        E(id="m4", name="M4", salary=140_000, gender="male", level="L4",
          job_family="Engineering", location="Remote", tenure_years=3),
        E(id="f3", name="F3", salary=130_000, gender="female", level="L4",
          job_family="Engineering", location="Remote", tenure_years=3),
    ]


CONTROLS = ("level", "job_family", "location", "tenure_band")


# ===========================================================================
# 1. PAY EQUITY — adjusted-gap math
# ===========================================================================
def test_pe_01_raw_gap_worked_example():
    emps = _worked_example()
    raw = pe.raw_gap(emps, "gender", "male", "female")
    # mean M = 120000, mean F = 104666.67
    assert raw["reference_mean"] == 120_000.0
    assert raw["group_mean"] == 104_666.67
    assert raw["gap_abs"] == 15_333.33
    assert raw["gap_pct"] == 0.1278  # 12.78% raw


def test_pe_02_adjusted_gap_controls_applied_worked_example():
    emps = _worked_example()
    adj = pe.adjusted_gap(emps, "gender", "male", "female", CONTROLS)
    # controlling for level collapses the gap from 12.78% to 7.65%
    assert adj["adjusted_gap_abs"] == 8_666.67
    assert adj["adjusted_gap_pct"] == 0.0765
    assert adj["controls_applied"] == list(CONTROLS)
    # two comparable cohorts (L3, L4), each has both groups
    assert len(adj["comparable_cohorts"]) == 2
    assert adj["group_n_compared"] == 3  # 2 women at L3 + 1 at L4


def test_pe_03_adjusted_below_raw_composition_effect():
    emps = _worked_example()
    raw = pe.raw_gap(emps, "gender", "male", "female")["gap_pct"]
    adj = pe.adjusted_gap(emps, "gender", "male", "female", CONTROLS)["adjusted_gap_pct"]
    # part of the raw gap is EXPLAINED by women being concentrated at the lower level
    assert adj < raw
    explained = round(raw - adj, 4)
    assert explained == 0.0513  # 12.78% - 7.65%


def test_pe_04_dropped_cohort_insufficient_comparison():
    E = pe.PEEmployee
    emps = [
        E(id="a", name="A", salary=100_000, gender="male", level="L3",
          job_family="Eng", location="Remote", tenure_years=3),
        E(id="b", name="B", salary=90_000, gender="female", level="L4",  # different level -> no male peer
          job_family="Eng", location="Remote", tenure_years=3),
    ]
    adj = pe.adjusted_gap(emps, "gender", "male", "female", CONTROLS)
    assert adj["comparable_cohorts"] == []
    assert len(adj["dropped_cohorts"]) == 2  # each cohort has only one group
    assert adj["group_n_compared"] == 0
    assert adj["adjusted_gap_pct"] == 0.0  # nothing comparable -> zero, no crash


def test_pe_05_threshold_flag_over_5pct():
    emps = _worked_example()
    an = pe.analyze(emps, attr="gender", threshold=0.05)
    fem = next(g for g in an["groups"] if g["group"] == "female")
    assert fem["adjusted_gap_pct"] == 0.0765
    assert fem["exceeds_threshold"] is True   # 7.65% > 5%
    assert an["directive_ready"] is False


def test_pe_06_threshold_flag_under_threshold_ready():
    # equal pay within every cohort -> adjusted gap 0 -> directive-ready
    E = pe.PEEmployee
    emps = [
        E(id="a", name="A", salary=100_000, gender="male", level="L3",
          job_family="Eng", location="Remote", tenure_years=3),
        E(id="b", name="B", salary=100_000, gender="female", level="L3",
          job_family="Eng", location="Remote", tenure_years=3),
    ]
    an = pe.analyze(emps, attr="gender", threshold=0.05)
    # equal means -> reference tie broken alphabetically; exactly one non-ref group
    assert len(an["groups"]) == 1
    grp = an["groups"][0]
    assert grp["adjusted_gap_pct"] == 0.0
    assert grp["exceeds_threshold"] is False
    assert an["directive_ready"] is True


def test_pe_07_remediation_budget_worked_example():
    emps = _worked_example()
    rem = pe.remediation_plan(emps, attr="gender", threshold=0.05, controls=CONTROLS)
    # floors: L3 -> 100k*.95 = 95k (F1 +5k, F2 +1k); L4 -> 140k*.95=133k (F3 +3k)
    assert rem["total_budget"] == 9_000.0
    assert rem["n_employees_adjusted"] == 3
    by_name = {a["name"]: a for a in rem["adjustments"]}
    assert by_name["F1"]["suggested_adjustment"] == 5_000.0
    assert by_name["F2"]["suggested_adjustment"] == 1_000.0
    assert by_name["F3"]["suggested_adjustment"] == 3_000.0
    assert by_name["F1"]["new_salary"] == 95_000.0


def test_pe_08_remediation_closes_gap_to_threshold():
    emps = _worked_example()
    rem = pe.remediation_plan(emps, attr="gender", threshold=0.05, controls=CONTROLS)
    for a in rem["adjustments"]:
        for e in emps:
            if e.id == a["employee_id"]:
                e.salary = a["new_salary"]
    adj = pe.adjusted_gap(emps, "gender", "male", "female", CONTROLS)
    assert adj["adjusted_gap_pct"] == 0.05  # exactly at threshold after remediation


def test_pe_09_segment_breakdown_by_job_category():
    emps = _worked_example()
    an = pe.analyze(emps, attr="gender", threshold=0.05)
    cats = {c["job_category"]: c for c in an["job_categories"]}
    assert "Engineering · L3" in cats and "Engineering · L4" in cats
    # within L3 the raw and adjusted gap should both flag (women underpaid)
    assert cats["Engineering · L3"]["headcount"] == 4
    assert cats["Engineering · L4"]["headcount"] == 3


def test_pe_10_reference_group_is_highest_paid():
    emps = _worked_example()
    an = pe.analyze(emps, attr="gender")
    assert an["reference_group"] == "male"   # highest mean pay -> reference


def test_pe_11_employee_position_vs_cohort():
    emps = _worked_example()
    pos = pe.employee_position(emps, "f1", attr="gender")
    assert pos["cohort"]["level"] == "L3"
    assert pos["cohort_size"] == 4                       # L3 remote 2-5y
    assert pos["cohort_mean"] == 96_000.0                # (100+100+90+94)/4
    assert pos["reference_group"] == "male"
    assert pos["reference_group_mean"] == 100_000.0
    assert pos["gap_vs_reference_abs"] == 10_000.0       # 100k - 90k


def test_pe_12_failsoft_single_group_and_empty():
    E = pe.PEEmployee
    one_group = [E(id="a", name="A", salary=100_000, gender="male", level="L3")]
    an = pe.analyze(one_group, attr="gender")
    assert an["available"] is False and "two groups" in an["reason"]
    empty = pe.analyze([], attr="gender")
    assert empty["available"] is False
    rem = pe.remediation_plan([], attr="gender")
    assert rem["available"] is False and rem["total_budget"] == 0.0


def test_pe_13_org_scoping_two_orgs_independent():
    o1, o2 = _fresh_pe_org(), _fresh_pe_org()
    pe.set_employees(o1, _worked_example())
    pe.set_employees(o2, [pe.PEEmployee(id="z", name="Z", salary=1, gender="male", level="L1")])
    a1 = pe.org_analysis(o1, attr="gender")
    a2 = pe.org_analysis(o2, attr="gender")
    assert a1["available"] is True and a1["headcount"] == 7
    assert a2["available"] is False          # only one group in org2
    # org1 analysis unaffected by org2
    assert a1["reference_group"] == "male"


def test_pe_14_compliance_report_shape():
    org = _fresh_pe_org()
    pe.set_employees(org, _worked_example())
    rep = pe.compliance_report(org, attr="gender", threshold=0.05)
    assert "EU Pay Transparency Directive" in rep["framework"]
    assert rep["reporting_threshold"] == 0.05
    assert rep["remediation_budget"] == 9_000.0
    assert rep["directive_ready"] is False
    assert rep["controls_applied"] == list(pe.DEFAULT_CONTROLS)


# ===========================================================================
# 2. CANDIDATE INTEGRITY — deterministic fraud scoring
# ===========================================================================
def test_ci_01_all_signals_high_risk_worked_example():
    signals = {
        # identity: 2/3 mismatch -> sev .6667 * 25 = 16.67
        "name_match": False, "email_matches_resume": False, "resume_matches_interview": True,
        # proxy: 3/3 flags -> sev 1.0 * 25 = 25
        "voice_change_flag": True, "face_change_flag": True, "multiple_faces_detected": True,
        # ai-gen: uniformity .8, latency .6, paste 5/5=1 -> mean .8 * 20 = 16
        "response_uniformity": 0.8, "latency_anomaly": 0.6, "paste_burst_count": 5,
        # location: 2/3 -> sev .6667 * 15 = 10
        "vpn_detected": True, "geo_ip_mismatch": True, "timezone_mismatch": False,
        # reference: 1/2 -> .5 * 10 = 5
        "reference_mismatches": 1, "references_total": 2,
        # resume: 1/3 -> .3333 * 5 = 1.67
        "inflated_titles": True, "unverifiable_employers": False, "suspicious_date_gaps": False,
    }
    out = ci.score_candidate(signals)
    # 16.67 + 25 + 16 + 10 + 5 + 1.67 = 74.34 -> round 74
    assert out["fraud_score"] == 74
    assert out["band"] == "high_risk"
    assert out["recommended_action"] == "block"
    assert out["confidence"] == 1.0
    assert out["categories_with_data"] == 6


def test_ci_02_category_points_breakdown():
    signals = {
        "voice_change_flag": True, "face_change_flag": True, "multiple_faces_detected": True,
    }
    out = ci.score_candidate(signals)
    proxy = next(c for c in out["contributing_signals"] if c["category"] == "proxy_interview")
    assert proxy["present"] is True
    assert proxy["severity"] == 1.0
    assert proxy["points"] == 25.0
    # only one category had data
    assert out["fraud_score"] == 25
    assert out["categories_with_data"] == 1


def test_ci_03_band_thresholds():
    assert ci.band_for(0) == "clear"
    assert ci.band_for(29) == "clear"
    assert ci.band_for(30) == "review"
    assert ci.band_for(59) == "review"
    assert ci.band_for(60) == "high_risk"
    assert ci.band_for(100) == "high_risk"
    assert ci.ACTION_BY_BAND["clear"] == "proceed"
    assert ci.ACTION_BY_BAND["review"] == "verify"
    assert ci.ACTION_BY_BAND["high_risk"] == "block"


def test_ci_04_clean_candidate_proceeds():
    signals = {
        "name_match": True, "email_matches_resume": True, "resume_matches_interview": True,
        "voice_change_flag": False, "face_change_flag": False, "multiple_faces_detected": False,
        "response_uniformity": 0.0, "latency_anomaly": 0.0, "paste_burst_count": 0,
        "vpn_detected": False, "geo_ip_mismatch": False, "timezone_mismatch": False,
        "reference_mismatches": 0, "references_total": 3,
        "inflated_titles": False, "unverifiable_employers": False, "suspicious_date_gaps": False,
    }
    out = ci.score_candidate(signals)
    assert out["fraud_score"] == 0
    assert out["band"] == "clear"
    assert out["recommended_action"] == "proceed"
    assert out["confidence"] == 1.0


def test_ci_05_missing_signals_failsoft_lower_confidence():
    # only identity present, one mismatch of three
    out = ci.score_candidate({"name_match": False, "email_matches_resume": True,
                              "resume_matches_interview": True})
    assert out["categories_with_data"] == 1
    assert out["confidence"] == round(1 / 6, 4)
    assert out["low_confidence"] is True
    # 1/3 mismatch * 25 = 8.33 -> 8
    assert out["fraud_score"] == 8
    assert out["band"] == "clear"
    # empty signals never crashes
    empty = ci.score_candidate({})
    assert empty["fraud_score"] == 0 and empty["confidence"] == 0.0
    assert empty["categories_with_data"] == 0


def test_ci_06_review_band_recommended_action():
    # proxy 2/3 (16.67) + ai-gen uniformity 1.0 (20) = 36.67 -> 37 review
    signals = {
        "voice_change_flag": True, "face_change_flag": True, "multiple_faces_detected": False,
        "response_uniformity": 1.0, "latency_anomaly": 1.0, "paste_burst_count": 5,
    }
    out = ci.score_candidate(signals)
    assert out["fraud_score"] == 37
    assert out["band"] == "review"
    assert out["recommended_action"] == "verify"


def test_ci_07_top_drivers_sorted():
    signals = {
        "name_match": False, "email_matches_resume": False, "resume_matches_interview": False,  # 25
        "vpn_detected": True, "geo_ip_mismatch": False, "timezone_mismatch": False,  # 5
    }
    out = ci.score_candidate(signals)
    assert out["top_drivers"][0]["category"] == "identity_consistency"
    assert out["top_drivers"][0]["points"] == 25.0


def test_ci_08_store_and_queue_org_scoped():
    o1, o2 = str(uuid.uuid4()), str(uuid.uuid4())
    ci.assess(o1, candidate_id="c1", candidate_name="Risky",
              signals={"voice_change_flag": True, "face_change_flag": True,
                       "multiple_faces_detected": True})  # 25 -> clear... bump higher
    ci.assess(o1, candidate_id="c2", candidate_name="VeryRisky",
              signals={"name_match": False, "email_matches_resume": False,
                       "resume_matches_interview": False,
                       "voice_change_flag": True, "face_change_flag": True,
                       "multiple_faces_detected": True})  # 25+25=50 review
    ci.assess(o2, candidate_id="c3", candidate_name="Other",
              signals={"vpn_detected": True})
    q1 = ci.review_queue(o1, min_band="review")
    assert q1["summary"]["total_assessed"] == 2
    assert q1["summary"]["flagged"] == 1                 # only c2 >= review
    assert q1["items"][0]["candidate_id"] == "c2"
    # org2 isolated
    q2 = ci.review_queue(o2, min_band="review")
    assert q2["summary"]["total_assessed"] == 1
    assert ci.get_candidate(o2, "c1") is None            # c1 belongs to org1
    assert ci.get_candidate(o1, "c1") is not None


# ===========================================================================
# 3. EXPLAINABLE SCORING + HITL RECOURSE
# ===========================================================================
def _build_submitted_scorecard(interview_id: str, competencies: list[str],
                                ratings: dict[str, int], evidence: dict[str, list[str]],
                                interviewer_id="int-1", name="Reviewer",
                                overall=3, conf=4):
    card = sc.upsert_scorecard(interview_id=interview_id, interviewer_id=interviewer_id,
                               interviewer_name=name, competencies=competencies)
    for comp in competencies:
        sc.update_competency(interview_id=interview_id, scorecard_id=card.id, competency=comp,
                             rating=ratings.get(comp), evidence_snippets=evidence.get(comp, []))
    sc.submit_scorecard(interview_id=interview_id, scorecard_id=card.id,
                        overall_rating=overall, overall_recommendation="hire",
                        interviewer_confidence=conf)
    return card


def test_sr_01_explanation_rubric_sums_correctly():
    iv = f"iv-{uuid.uuid4()}"
    _build_submitted_scorecard(
        iv, ["communication", "technical_depth"],
        ratings={"communication": 4, "technical_depth": 2},
        evidence={"communication": ["walked through the design clearly"],
                  "technical_depth": ["described the caching trade-off"]},
    )
    exp = sr.build_explanation("orgA", iv)
    assert exp["available"] is True
    assert len(exp["rubric"]) == 2
    # equal weights -> 0.5 each, sum to 1.0
    assert exp["weights_sum"] == 1.0
    # overall = 0.5*4 + 0.5*2 = 3.0 == sum of weighted_contribution
    assert exp["overall_score"] == 3.0
    total = round(sum(r["weighted_contribution"] for r in exp["rubric"]), 4)
    assert total == exp["overall_score"]


def test_sr_02_evidence_attached_to_dimensions():
    iv = f"iv-{uuid.uuid4()}"
    _build_submitted_scorecard(
        iv, ["communication"],
        ratings={"communication": 3},
        evidence={"communication": ["explained the migration plan", "summarised the risk"]},
    )
    exp = sr.build_explanation("orgA", iv)
    comm = exp["rubric"][0]
    assert comm["dimension"] == "communication"
    assert len(comm["evidence"]) == 2
    assert comm["evidence"][0]["quote"] == "explained the migration plan"
    assert comm["evidence_gap"] is False


def test_sr_03_evidence_gap_lowers_confidence():
    iv = f"iv-{uuid.uuid4()}"
    _build_submitted_scorecard(
        iv, ["ownership"], ratings={"ownership": 3}, evidence={"ownership": []},
    )
    exp = sr.build_explanation("orgA", iv)
    own = exp["rubric"][0]
    assert own["evidence_gap"] is True
    # no evidence -> evidence_ratio 0; single rater -> agreement 1; conf 4/5=.8
    # confidence = .4*0 + .4*1 + .2*.8 = 0.56
    assert own["confidence"] == 0.56


def test_sr_04_weighted_custom_weights():
    iv = f"iv-{uuid.uuid4()}"
    _build_submitted_scorecard(
        iv, ["communication", "technical_depth"],
        ratings={"communication": 4, "technical_depth": 2},
        evidence={"communication": ["x"], "technical_depth": ["y"]},
    )
    # weight technical_depth 3x communication -> normalised .25 / .75
    exp = sr.build_explanation("orgA", iv, weights={"communication": 1, "technical_depth": 3})
    assert exp["weights_sum"] == 1.0
    # overall = .25*4 + .75*2 = 2.5
    assert exp["overall_score"] == 2.5


def test_sr_05_failsoft_no_scorecards():
    exp = sr.build_explanation("orgA", f"iv-{uuid.uuid4()}")
    assert exp["available"] is False
    assert exp["overall_score"] == 0.0
    assert exp["human_reviewable"] is True
    assert exp["ai_disclosure"] == "AI-assisted, human-reviewable"


def test_sr_06_compliance_mapping_present():
    exp = sr.build_explanation("orgA", f"iv-{uuid.uuid4()}")
    frameworks = {c["framework"] for c in exp["compliance"]}
    assert "NYC Local Law 144" in frameworks
    assert any("EU AI Act" in f for f in frameworks)
    assert any("Colorado" in f for f in frameworks)


def test_sr_07_hitl_open_review_audit_trail():
    org, iv = "orgH", f"iv-{uuid.uuid4()}"
    rv = sr.open_review(org, iv, dimension="communication",
                        reason="candidate disputes the score",
                        requested_by="cand@x.com", requested_by_role="candidate",
                        original_rating=2.0)
    assert rv["status"] == "open"
    assert rv["ai_disclosure"] == "AI-assisted, human-reviewable"
    assert len(rv["audit_trail"]) == 1
    assert rv["audit_trail"][0]["action"] == "review_opened"
    assert rv["audit_trail"][0]["actor"] == "cand@x.com"


def test_sr_08_hitl_adjust_records_original_and_new():
    org, iv = "orgH2", f"iv-{uuid.uuid4()}"
    rv = sr.open_review(org, iv, dimension="technical_depth",
                        reason="evidence overlooked", requested_by="rec@x.com",
                        requested_by_role="recruiter", original_rating=2.0)
    adj = sr.adjust_review(org, iv, rv["id"], reviewer="hr@x.com",
                           adjusted_rating=3.0, reason="added evidence on merge")
    assert adj["status"] == "resolved"
    assert adj["original_rating"] == 2.0
    assert adj["adjusted_rating"] == 3.0
    assert adj["reviewer"] == "hr@x.com"
    # audit trail now has open + adjust
    actions = [e["action"] for e in adj["audit_trail"]]
    assert actions == ["review_opened", "score_adjusted"]
    assert adj["audit_trail"][1]["from_rating"] == 2.0
    assert adj["audit_trail"][1]["to_rating"] == 3.0


def test_sr_09_reviews_surface_in_explanation_and_org_scoped():
    org, iv = "orgH3", f"iv-{uuid.uuid4()}"
    _build_submitted_scorecard(iv, ["communication"], ratings={"communication": 3},
                               evidence={"communication": ["said x"]})
    sr.open_review(org, iv, dimension="communication", reason="dispute",
                   requested_by="c@x", requested_by_role="candidate", original_rating=3.0)
    exp = sr.build_explanation(org, iv)
    assert len(exp["reviews"]) == 1
    # a different org sees no reviews for the same interview id
    exp2 = sr.build_explanation("orgOther", iv)
    assert exp2["reviews"] == []


def test_sr_10_adjust_missing_review_returns_none():
    assert sr.adjust_review("orgX", "ivX", "nope", reviewer="r", adjusted_rating=3, reason="x") is None


# ===========================================================================
# HTTP boundary — role gating + org scoping
# ===========================================================================
def _as(role: str, org: str) -> Actor:
    return Actor(user_id=str(uuid.uuid4()), org_id=org, role=role,
                 claims={"email": f"{role}@x.com"})


def test_http_01_pay_equity_role_gate_and_analysis():
    org = _fresh_pe_org()
    pe.set_employees(org, _worked_example())
    client = TestClient(app)
    # employee is blocked from pay data
    app.dependency_overrides[require_org] = lambda: _as("employee", org)
    assert client.get("/api/pay-equity/analysis").status_code == 403
    # hr can read the analysis
    app.dependency_overrides[require_org] = lambda: _as("hr", org)
    r = client.get("/api/pay-equity/analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["reference_group"] == "male"
    assert body["directive_ready"] is False
    # remediation plan endpoint
    rp = client.post("/api/pay-equity/remediation-plan", json={"threshold": 0.05})
    assert rp.status_code == 200
    assert rp.json()["total_budget"] == 9_000.0
    app.dependency_overrides.clear()


def test_http_02_candidate_integrity_assess_and_queue():
    org = str(uuid.uuid4())
    client = TestClient(app)
    app.dependency_overrides[require_org] = lambda: _as("recruiter", org)
    r = client.post("/api/candidate-integrity/assess", json={
        "candidate_id": "cand-1", "candidate_name": "Test",
        "signals": {"voice_change_flag": True, "face_change_flag": True,
                    "multiple_faces_detected": True,
                    "name_match": False, "email_matches_resume": False,
                    "resume_matches_interview": False},
    })
    assert r.status_code == 200
    assert r.json()["fraud_score"] == 50 and r.json()["band"] == "review"
    q = client.get("/api/candidate-integrity/queue")
    assert q.status_code == 200 and q.json()["summary"]["flagged"] == 1
    # employee role blocked
    app.dependency_overrides[require_org] = lambda: _as("employee", org)
    assert client.post("/api/candidate-integrity/assess",
                       json={"candidate_id": "x"}).status_code == 403
    app.dependency_overrides.clear()


def test_http_03_interview_score_review_flow():
    org = str(uuid.uuid4())
    iv = f"iv-{uuid.uuid4()}"
    _build_submitted_scorecard(iv, ["communication"], ratings={"communication": 2},
                               evidence={"communication": ["said x"]})
    client = TestClient(app)
    app.dependency_overrides[require_org] = lambda: _as("recruiter", org)
    exp = client.get(f"/api/interviews/{iv}/score-explanation")
    assert exp.status_code == 200 and exp.json()["available"] is True
    opened = client.post(f"/api/interviews/{iv}/score-review",
                         json={"dimension": "communication", "reason": "dispute",
                               "original_rating": 2.0})
    assert opened.status_code == 200
    rid = opened.json()["id"]
    # recruiter cannot adjust (only hr/manager/owner/admin)
    bad = client.patch(f"/api/interviews/{iv}/score-review/{rid}",
                       json={"adjusted_rating": 3.0, "reason": "fixed"})
    assert bad.status_code == 403
    # hr can adjust
    app.dependency_overrides[require_org] = lambda: _as("hr", org)
    good = client.patch(f"/api/interviews/{iv}/score-review/{rid}",
                        json={"adjusted_rating": 3.0, "reason": "evidence added"})
    assert good.status_code == 200 and good.json()["status"] == "resolved"
    app.dependency_overrides.clear()
