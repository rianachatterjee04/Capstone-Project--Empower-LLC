"""HTTP tests for POST /ai-interview/sessions/{id}/evaluate.

The live model is never called. An autouse fixture pins llm_complete to None
on the evaluator, the adaptive engine, and the interview service. Tests of the
AI path patch answer_evaluation_service.llm_complete with a fixed JSON reply.

Run:  python -m pytest tests/test_ai_interview_evaluate_endpoint.py -v
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.api.deps import Actor, db_session, require_org
from app.api.routers import ai_interview as ai_router
from app.main import app
from app.services import adaptive_interview_service as adaptive
from app.services import ai_interview_service as interview_svc
from app.services import answer_evaluation_service as evaluator


_ANSWER = (
    "I shipped the billing migration and cut latency by 40 percent. "
    "I owned the rollout and the on-call runbook."
)
_QUOTE = "I shipped the billing migration and cut latency by 40 percent."


@pytest.fixture(autouse=True)
def _no_live_llm():
    with (
        patch.object(evaluator, "llm_complete", None),
        patch.object(adaptive, "llm_complete", None),
        patch.object(interview_svc, "llm_complete", None),
    ):
        yield


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


def _llm_json():
    return json.dumps({
        "rating": 3,
        "evidence": [_QUOTE],
        "strengths": ["Specific measurable outcome"],
        "concerns": [],
        "rationale": "The candidate described what they shipped and the result.",
    })


def _start(c: TestClient) -> dict:
    r = c.post("/api/ai-interview/sessions", json={
        "job_title": "Backend Engineer",
        "n_questions": 5,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _answer_n(c: TestClient, n: int = 2) -> tuple[str, list[str]]:
    sess = _start(c)
    sid = sess["id"]
    qid = sess["current_question_id"]
    answered: list[str] = []
    for _ in range(n):
        r = c.post(f"/api/ai-interview/sessions/{sid}/answer", json={
            "question_id": qid,
            "answer": _ANSWER,
        })
        assert r.status_code == 200, r.text
        answered.append(qid)
        nxt = r.json().get("next") or {}
        if nxt.get("done") or "question" not in nxt:
            break
        qid = nxt["question"]["id"]
    assert len(answered) == n, f"only answered {answered}"
    return sid, answered


def test_evaluate_returns_one_entry_per_answered_question():
    org = str(uuid.uuid4())
    c = _client_for("recruiter", org)
    try:
        sid, answered = _answer_n(c, 2)
        r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == sid
        assert body["evaluated"] == 2
        assert [e["question_id"] for e in body["evaluations"]] == answered
        for entry in body["evaluations"]:
            assert entry["question_id"]
            assert entry["question"]
            assert "rating" in entry
            assert isinstance(entry["evidence"], list)
            assert entry["evaluated_by"] in ("llm", "rules")
        assert body["fairness_note"].strip()
    finally:
        app.dependency_overrides.clear()


def test_evaluate_uses_llm_when_the_reply_quotes_the_answer():
    org = str(uuid.uuid4())
    c = _client_for("hr", org)
    try:
        sid, _answered = _answer_n(c, 1)
        with patch.object(evaluator, "llm_complete", return_value=_llm_json()):
            r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["evaluated"] == 1
        assert body["evaluations"][0]["evaluated_by"] == "llm"
        assert _QUOTE in body["evaluations"][0]["evidence"]
    finally:
        app.dependency_overrides.clear()


def test_evaluate_falls_back_to_rules_when_llm_is_unavailable():
    org = str(uuid.uuid4())
    c = _client_for("manager", org)
    try:
        sid, _answered = _answer_n(c, 1)
        r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 200, r.text
        assert r.json()["evaluations"][0]["evaluated_by"] == "rules"
    finally:
        app.dependency_overrides.clear()


def test_question_id_filter_and_unknown_id():
    org = str(uuid.uuid4())
    c = _client_for("recruiter", org)
    try:
        sid, answered = _answer_n(c, 2)
        only = c.post(
            f"/api/ai-interview/sessions/{sid}/evaluate",
            params={"question_id": answered[0]},
        )
        assert only.status_code == 200, only.text
        body = only.json()
        assert body["evaluated"] == 1
        assert [e["question_id"] for e in body["evaluations"]] == [answered[0]]

        bad = c.post(
            f"/api/ai-interview/sessions/{sid}/evaluate",
            params={"question_id": "not-a-question"},
        )
        assert bad.status_code == 400
        assert bad.json()["detail"] == "Unknown question_id"
    finally:
        app.dependency_overrides.clear()


def test_session_with_no_answers_returns_an_empty_list():
    org = str(uuid.uuid4())
    c = _client_for("admin", org)
    try:
        sid = _start(c)["id"]
        r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["evaluated"] == 0
        assert body["evaluations"] == []
    finally:
        app.dependency_overrides.clear()


def test_http_org_scoping_blocks_other_org():
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    c = _client_for("recruiter", org_a)
    try:
        sid = _start(c)["id"]
    finally:
        app.dependency_overrides.clear()
    c2 = _client_for("recruiter", org_b)
    try:
        r = c2.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_http_role_gating_blocks_employee():
    org = str(uuid.uuid4())
    c = _client_for("employee", org)
    try:
        r = c.post(f"/api/ai-interview/sessions/{uuid.uuid4()}/evaluate")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_evaluator_failure_is_reported_without_failing_the_request():
    org = str(uuid.uuid4())
    c = _client_for("owner", org)
    try:
        sid, answered = _answer_n(c, 2)

        def _boom(**_kwargs):
            raise RuntimeError("model down")

        with patch.object(evaluator, "evaluate_answer", side_effect=_boom):
            r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["evaluated"] == 2
        assert [e["question_id"] for e in body["evaluations"]] == answered
        for entry in body["evaluations"]:
            assert entry["evaluated_by"] == "unavailable"
            assert entry["rating"] is None
            assert entry["rating_label"] == "pending"
            assert entry["evidence"] == []
            assert entry["strengths"] == []
            assert entry["concerns"] == ["Evaluation unavailable."]
            assert entry["truncated"] is False
    finally:
        app.dependency_overrides.clear()


def test_lock_is_not_held_during_evaluation():
    org = str(uuid.uuid4())
    c = _client_for("recruiter", org)
    acquired: list[bool] = []

    def _probe(**_kwargs):
        ok = ai_router._lock.acquire(blocking=False)
        acquired.append(ok)
        if ok:
            ai_router._lock.release()
        return {
            "competency": _kwargs.get("competency", ""),
            "rating": 2,
            "rating_label": "lean_hire",
            "evidence": [],
            "strengths": [],
            "concerns": [],
            "rationale": "probe",
            "evaluated_by": "llm",
            "truncated": False,
        }

    try:
        sid, _answered = _answer_n(c, 1)
        with patch.object(evaluator, "evaluate_answer", side_effect=_probe):
            r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 200, r.text
        assert acquired, "the evaluator was never called"
        assert all(acquired), "the session lock was still held on the worker thread"
    finally:
        app.dependency_overrides.clear()
