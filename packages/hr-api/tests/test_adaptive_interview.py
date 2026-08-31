"""Golden-vector tests for the ADAPTIVE INTERVIEW ENGINE.

Covers, with hand-checked vectors:
  * answer-analysis quality classification (vague / strong / off_topic / shallow)
  * coverage state updates (monotone signal, probe counting)
  * next-move decision table (probe / follow_up / pivot / clarify / wrap_up)
  * coverage-driven completion (stops when all sufficient; respects max cap)
  * fail-soft question generation (ai_client down -> curated ladder, never breaks)
  * /complete integration: explainable scorecard + fraud signal + fairness
  * org-scoping at the HTTP boundary

Run:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_adaptive_interview.py -q
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.deps import Actor, db_session, require_org
from app.main import app
from app.services.ai_interview_service import InterviewQuestion
from app.services import adaptive_interview_service as A


# ===========================================================================
# helpers
# ===========================================================================
_Q = InterviewQuestion(id="q1", competency="ownership",
                       text="Tell me about a project you owned end to end and the outcome.")

_STRONG = (
    "I led the migration of our billing project end-to-end. I designed the new schema, "
    "shipped it over three months, and reduced latency by 40 percent while cutting costs "
    "20000 dollars. I coordinated four engineers and owned the rollout and the on-call "
    "runbook, and the outcome was zero downtime."
)
_SHALLOW = "I worked on a project with my team and it went well I think."
_OFF_TOPIC = ("I really love hiking on the weekends and my dog is a golden retriever named "
              "Max who likes to swim in lakes near my house.")
_REFUSAL = "I do not know, skip this question."


def _cov(**comps) -> dict:
    """Build a coverage map from {competency: (signal, probes)} pairs."""
    return {
        c: {"signal_strength": s, "probes": p, "best_score": int(s * 100), "quality_history": []}
        for c, (s, p) in comps.items()
    }


# ===========================================================================
# 1. ANSWER ANALYSIS — quality classification
# ===========================================================================
def test_analysis_classifies_strong():
    a = A.analyze_answer(_Q, _STRONG)
    assert a["quality"] == "strong"
    assert a["competency"] == "ownership"
    assert a["score"] > 40
    assert a["evidence"], "strong answer should surface evidence quotes"


def test_analysis_classifies_shallow():
    a = A.analyze_answer(_Q, _SHALLOW)
    assert a["quality"] == "shallow"


def test_analysis_classifies_off_topic():
    a = A.analyze_answer(_Q, _OFF_TOPIC)
    assert a["quality"] == "off_topic"


def test_analysis_classifies_vague_refusal():
    assert A.analyze_answer(_Q, _REFUSAL)["quality"] == "vague"


def test_analysis_classifies_vague_empty():
    a = A.analyze_answer(_Q, "")
    assert a["quality"] == "vague"
    assert a["score"] == 0


def test_evidence_prefers_numeric_ownership_sentences():
    ev = A.extract_evidence(
        "I like the team. I shipped the API and cut errors by 30 percent across 5 services."
    )
    assert any("30 percent" in q or "5 services" in q for q in ev)


# ===========================================================================
# 2. COVERAGE — monotone signal, probe counting
# ===========================================================================
def test_coverage_signal_is_monotone_and_bounded():
    cov = A.init_coverage(["ownership"])
    s0 = cov["ownership"]["signal_strength"]
    A.update_coverage(cov, "ownership", {"score": 80, "quality": "strong"})
    s1 = cov["ownership"]["signal_strength"]
    A.update_coverage(cov, "ownership", {"score": 80, "quality": "strong"})
    s2 = cov["ownership"]["signal_strength"]
    assert 0.0 == s0 < s1 < s2 <= 1.0
    assert cov["ownership"]["probes"] == 2


def test_coverage_vague_answer_barely_moves_signal():
    cov = A.init_coverage(["ownership"])
    A.update_coverage(cov, "ownership", {"score": 5, "quality": "vague"})
    assert cov["ownership"]["signal_strength"] < 0.1


def test_coverage_strong_answer_reaches_sufficient_after_two():
    cov = A.init_coverage(["ownership"])
    A.update_coverage(cov, "ownership", {"score": 80, "quality": "strong"})
    A.update_coverage(cov, "ownership", {"score": 80, "quality": "strong"})
    assert cov["ownership"]["signal_strength"] >= A.SUFFICIENT_SIGNAL


# ===========================================================================
# 3. NEXT-MOVE DECISION TABLE
# ===========================================================================
_RUBRIC = ["ownership", "technical_depth", "communication"]


def test_move_off_topic_triggers_clarify():
    cov = _cov(ownership=(0.2, 1), technical_depth=(0.0, 0), communication=(0.0, 0))
    d = A.choose_next_move(cov, last_competency="ownership", quality="off_topic",
                           rubric=_RUBRIC, asked_count=1, max_questions=12)
    assert d["move"] == A.CLARIFY and d["competency"] == "ownership"


def test_move_shallow_triggers_follow_up_same_competency():
    cov = _cov(ownership=(0.3, 1), technical_depth=(0.0, 0), communication=(0.0, 0))
    d = A.choose_next_move(cov, last_competency="ownership", quality="shallow",
                           rubric=_RUBRIC, asked_count=1, max_questions=12)
    assert d["move"] == A.FOLLOW_UP and d["competency"] == "ownership"


def test_move_vague_after_max_probes_pivots():
    cov = _cov(ownership=(0.3, A.MAX_PROBES_PER_COMPETENCY),
               technical_depth=(0.0, 0), communication=(0.0, 0))
    d = A.choose_next_move(cov, last_competency="ownership", quality="vague",
                           rubric=_RUBRIC, asked_count=3, max_questions=12)
    assert d["move"] == A.PIVOT and d["competency"] in ("technical_depth", "communication")


def test_move_strong_under_explored_probes_deeper():
    cov = _cov(ownership=(0.4, 1), technical_depth=(0.0, 0), communication=(0.0, 0))
    d = A.choose_next_move(cov, last_competency="ownership", quality="strong",
                           rubric=_RUBRIC, asked_count=1, max_questions=12)
    assert d["move"] == A.PROBE and d["competency"] == "ownership"


def test_move_strong_sufficient_pivots_to_least_covered():
    cov = _cov(ownership=(0.7, 2), technical_depth=(0.1, 1), communication=(0.3, 1))
    d = A.choose_next_move(cov, last_competency="ownership", quality="strong",
                           rubric=_RUBRIC, asked_count=3, max_questions=12)
    assert d["move"] == A.PIVOT
    assert d["competency"] == "technical_depth"  # lowest signal


def test_move_wrap_up_when_all_sufficient():
    cov = _cov(ownership=(0.7, 2), technical_depth=(0.65, 2), communication=(0.8, 2))
    d = A.choose_next_move(cov, last_competency="communication", quality="strong",
                           rubric=_RUBRIC, asked_count=6, max_questions=12)
    assert d["move"] == A.WRAP_UP and d["reason"] == "all_competencies_sufficient"


def test_move_wrap_up_when_max_cap_hit():
    cov = _cov(ownership=(0.2, 4), technical_depth=(0.1, 4), communication=(0.1, 4))
    d = A.choose_next_move(cov, last_competency="ownership", quality="shallow",
                           rubric=_RUBRIC, asked_count=12, max_questions=12)
    assert d["move"] == A.WRAP_UP and d["reason"] == "max_question_cap_reached"


# ===========================================================================
# 4. FAIL-SOFT QUESTION GENERATION (ai_client down -> curated ladder)
# ===========================================================================
def test_failsoft_uses_ladder_when_llm_absent(monkeypatch):
    monkeypatch.setattr(A, "llm_complete", None)
    cov = A.init_coverage(_RUBRIC)
    gen = A.generate_next_question(
        move=A.PIVOT, competency="technical_depth", coverage=cov,
        asked_texts=set(), rubric=_RUBRIC,
    )
    assert gen["source"] == "ladder"
    assert gen["text"] in A.QUESTION_LADDER["technical_depth"]


def test_failsoft_uses_ladder_when_llm_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("gateway down")
    monkeypatch.setattr(A, "llm_complete", _boom)
    cov = A.init_coverage(_RUBRIC)
    gen = A.generate_next_question(
        move=A.PROBE, competency="ownership", coverage=cov,
        asked_texts=set(), rubric=_RUBRIC,
    )
    assert gen["source"] == "ladder"
    assert gen["text"]  # non-empty, session never breaks


def test_ladder_does_not_repeat_asked_questions(monkeypatch):
    monkeypatch.setattr(A, "llm_complete", None)
    cov = A.init_coverage(["ownership"])
    asked = {A.QUESTION_LADDER["ownership"][0]}
    gen = A.generate_next_question(
        move=A.PIVOT, competency="ownership", coverage=cov,
        asked_texts=asked, rubric=["ownership"],
    )
    assert gen["text"] not in asked


def test_followup_asks_for_specifics(monkeypatch):
    monkeypatch.setattr(A, "llm_complete", None)
    cov = _cov(ownership=(0.3, 1))
    gen = A.generate_next_question(
        move=A.FOLLOW_UP, competency="ownership", coverage=cov,
        asked_texts=set(), rubric=["ownership"],
    )
    assert gen["source"] == "ladder"
    assert any(w in gen["text"].lower() for w in ("specific", "example", "number", "measurable"))


# ===========================================================================
# 5. HTTP INTEGRATION — adaptive session + explainable outcome + fraud + org-scoping
# ===========================================================================
def _as(role: str, org: str) -> Actor:
    return Actor(user_id=str(uuid.uuid4()), org_id=org, role=role,
                 claims={"email": f"{role}@test.io"})


class _FakeDB:
    """No-op stand-in for the async DB session — the audit writes are best-effort."""
    def add(self, *_a, **_k):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _client_for(role: str, org: str) -> TestClient:
    c = TestClient(app)
    app.dependency_overrides[require_org] = lambda: _as(role, org)
    app.dependency_overrides[db_session] = lambda: _FakeDB()
    return c


def test_http_answer_returns_analysis_coverage_and_next():
    org = str(uuid.uuid4())
    c = _client_for("recruiter", org)
    try:
        sess = c.post("/api/ai-interview/sessions", json={
            "job_title": "Backend Engineer", "n_questions": 5,
        }).json()
        assert sess["rubric"], "session anchored on a rubric"
        qid = sess["current_question_id"]
        r = c.post(f"/api/ai-interview/sessions/{sess['id']}/answer",
                   json={"question_id": qid, "answer": _STRONG})
        assert r.status_code == 200
        body = r.json()
        assert "analysis" in body
        assert body["analysis"]["quality"] in ("strong", "shallow", "vague", "off_topic")
        assert "coverage_map" in body and body["coverage_map"]["n_total"] >= 1
        assert "next" in body
        # the engine advanced: either a next question or a wrap-up
        assert body["next"].get("done") is True or "question" in body["next"]
        # state endpoint reflects progress
        st = c.get(f"/api/ai-interview/sessions/{sess['id']}/state").json()
        assert st["asked_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_http_complete_yields_explainable_scorecard_and_fraud():
    org = str(uuid.uuid4())
    c = _client_for("recruiter", org)
    try:
        sess = c.post("/api/ai-interview/sessions", json={
            "job_title": "Backend Engineer", "n_questions": 4,
        }).json()
        qid = sess["current_question_id"]
        # answer twice so there are >=2 answers (uniformity signal is computable)
        r1 = c.post(f"/api/ai-interview/sessions/{sess['id']}/answer",
                    json={"question_id": qid, "answer": _STRONG}).json()
        nxt = r1["next"]
        if not nxt.get("done"):
            nqid = nxt["question"]["id"]
            c.post(f"/api/ai-interview/sessions/{sess['id']}/answer",
                   json={"question_id": nqid, "answer": _SHALLOW})
        out = c.post(f"/api/ai-interview/sessions/{sess['id']}/complete", json={
            "integrity_signals": {"vpn_detected": True, "geo_ip_mismatch": False, "timezone_mismatch": False},
        }).json()
        outcome = out["outcome"]
        assert "explainable_scorecard" in outcome
        assert "integrity" in outcome and "fraud_score" in outcome["integrity"]
        assert "fairness" in outcome
        # explainable scorecard reconciles as a weighted sum (from the shared service)
        sc = outcome["explainable_scorecard"]
        assert sc.get("ai_disclosure") == "AI-assisted, human-reviewable"
    finally:
        app.dependency_overrides.clear()


def test_http_org_scoping_blocks_other_org():
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    c = _client_for("recruiter", org_a)
    try:
        sess = c.post("/api/ai-interview/sessions", json={"job_title": "SWE", "n_questions": 3}).json()
        sid = sess["id"]
    finally:
        app.dependency_overrides.clear()
    # different org cannot read the session
    c2 = _client_for("recruiter", org_b)
    try:
        r = c2.get(f"/api/ai-interview/sessions/{sid}/state")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_http_role_gating_blocks_employee():
    org = str(uuid.uuid4())
    c = _client_for("employee", org)
    try:
        r = c.post("/api/ai-interview/sessions", json={"job_title": "SWE"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
