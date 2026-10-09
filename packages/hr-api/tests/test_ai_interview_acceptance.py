"""Acceptance checks for POST /ai-interview/sessions/{id}/evaluate.

Links an evaluation back to the candidate and job on that session, and checks
that several interviews can be scored without mixing.

Saving evaluations and showing them on a pipeline are not covered because
they are not built yet.

The live model is never called. An autouse fixture pins llm_complete to None
on the evaluator, the adaptive engine, and the interview service.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.api.deps import Actor, db_session, require_org
from app.main import app
from app.services import adaptive_interview_service as adaptive
from app.services import ai_interview_service as interview_svc
from app.services import answer_evaluation_service as evaluator


_ANSWER = (
    "I shipped the billing migration and cut latency by 40 percent. "
    "I owned the rollout and the on-call runbook."
)


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


def _start(
    c: TestClient,
    *,
    candidate_id: str | None = None,
    candidate_name: str | None = None,
    job_id: str | None = None,
    job_title: str = "Backend Engineer",
) -> dict:
    payload = {"job_title": job_title, "n_questions": 5}
    if candidate_id is not None:
        payload["candidate_id"] = candidate_id
    if candidate_name is not None:
        payload["candidate_name"] = candidate_name
    if job_id is not None:
        payload["job_id"] = job_id
    r = c.post("/api/ai-interview/sessions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _answer_n(c: TestClient, sid: str, n: int = 1) -> list[str]:
    state = c.get(f"/api/ai-interview/sessions/{sid}")
    assert state.status_code == 200, state.text
    qid = state.json()["current_question_id"]
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
    return answered


def test_evaluations_stay_linked_to_their_own_candidate_and_job():
    org = str(uuid.uuid4())
    c = _client_for("recruiter", org)
    people = [
        ("cand-ada", "Ada Okonkwo", "job-backend"),
        ("cand-bao", "Bao Chen", "job-design"),
        ("cand-cio", "Cio Rahman", "job-finance"),
    ]
    try:
        started = []
        for candidate_id, candidate_name, job_id in people:
            sess = _start(
                c,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                job_id=job_id,
                job_title=f"Role for {candidate_name}",
            )
            answered = _answer_n(c, sess["id"], 1)
            started.append((sess["id"], candidate_id, candidate_name, job_id, answered))

        for sid, candidate_id, candidate_name, job_id, answered in started:
            r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["session_id"] == sid
            assert body["candidate_id"] == candidate_id
            assert body["candidate_name"] == candidate_name
            assert body["job_id"] == job_id
            others = {p[0] for p in people if p[0] != candidate_id}
            assert body["candidate_id"] not in others
            other_jobs = {p[2] for p in people if p[2] != job_id}
            assert body["job_id"] not in other_jobs
            # The local question bank reuses ids. What must not mix is the
            # candidate and job this session's answers are scored under.
            assert [e["question_id"] for e in body["evaluations"]] == answered
            assert body["evaluated"] == len(answered)
    finally:
        app.dependency_overrides.clear()


def test_five_interviews_each_return_an_evaluation_per_answer():
    org = str(uuid.uuid4())
    c = _client_for("hr", org)
    try:
        sessions = []
        for i in range(5):
            sess = _start(
                c,
                candidate_id=f"cand-{i}",
                candidate_name=f"Candidate {i}",
                job_id=f"job-{i}",
                job_title=f"Role {i}",
            )
            answered = _answer_n(c, sess["id"], 1)
            sessions.append((sess["id"], answered))
        assert len(sessions) == 5
        for sid, answered in sessions:
            r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["evaluated"] == len(answered)
            assert [e["question_id"] for e in body["evaluations"]] == answered
    finally:
        app.dependency_overrides.clear()


def test_session_without_a_candidate_returns_null_ids_and_still_evaluates():
    org = str(uuid.uuid4())
    c = _client_for("admin", org)
    try:
        sess = _start(c, job_title="Open role")
        sid = sess["id"]
        answered = _answer_n(c, sid, 1)
        r = c.post(f"/api/ai-interview/sessions/{sid}/evaluate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["candidate_id"] is None
        assert body["candidate_name"] is None
        assert body["job_id"] is None
        assert body["evaluated"] == 1
        assert [e["question_id"] for e in body["evaluations"]] == answered
    finally:
        app.dependency_overrides.clear()


def test_several_answers_come_back_in_question_order():
    org = str(uuid.uuid4())
    c = _client_for("manager", org)
    try:
        sess = _start(
            c,
            candidate_id="cand-multi",
            candidate_name="Multi Answer",
            job_id="job-multi",
        )
        answered = _answer_n(c, sess["id"], 3)
        r = c.post(f"/api/ai-interview/sessions/{sess['id']}/evaluate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["evaluated"] == 3
        assert [e["question_id"] for e in body["evaluations"]] == answered
    finally:
        app.dependency_overrides.clear()
