"""HR governance seam for Trust CORTEX — the cross-domain contract endpoint.

Proves GET /api/governance/pending-decisions returns HR pending decisions
normalized to the cross-domain contract, that it is fail-soft when approval
tables are absent (still surfaces workforce-risk decisions), and that it maps
real pending approvals when they exist.

Run: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_governance_seam.py -q
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.deps import Actor, db_session, require_org
from app.main import app

ORG = "11111111-1111-1111-1111-111111111111"
UID = "22222222-2222-2222-2222-222222222222"

_CONTRACT_KEYS = {"id", "title", "trust_score", "urgency", "recommended_verdict",
                  "deep_link", "reason", "module"}


class _BrokenDB:
    """Every call raises → approval tables 'absent'; the endpoint must still
    return workforce-risk decisions and never 500."""
    async def execute(self, *a, **k):
        raise RuntimeError("db down")

    async def rollback(self):
        return None


class _RowsDB:
    """Returns one pending bank-account approval so the real-approval path is covered."""
    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return self

        def all(self):
            return self._rows

    async def execute(self, *a, **k):
        return self._Res([{
            "id": "app-1", "title": "Update payroll bank account",
            "type": "bank_account", "amount": 9000, "requested_by": "clerk@co",
            "created_at": None,
        }])

    async def rollback(self):
        return None


def _client(db) -> TestClient:
    app.dependency_overrides[require_org] = lambda: Actor(
        user_id=UID, org_id=ORG, role="owner", claims={"email": "x@y.z"})
    app.dependency_overrides[db_session] = lambda: db
    return TestClient(app)


def _reset():
    app.dependency_overrides.pop(require_org, None)
    app.dependency_overrides.pop(db_session, None)


def test_failsoft_returns_workforce_risk_decisions_when_approvals_absent():
    c = _client(_BrokenDB())
    try:
        r = c.get("/api/governance/pending-decisions")
        assert r.status_code == 200
        body = r.json()
        assert body["module"] == "hr"
        assert body["count"] >= 1  # workforce-risk engine alerts always present
        for d in body["decisions"]:
            assert d["module"] == "hr"
            assert _CONTRACT_KEYS.issubset(d.keys())
            assert d["recommended_verdict"] in ("approve", "challenge", "block")
            assert 0.0 <= d["trust_score"] <= 100.0
    finally:
        _reset()


def test_real_pending_approval_is_mapped_to_contract():
    c = _client(_RowsDB())
    try:
        body = c.get("/api/governance/pending-decisions").json()
        approvals = [d for d in body["decisions"] if d["id"].startswith("approval:")]
        assert approvals, "expected the pending bank-account approval to surface"
        a = approvals[0]
        assert a["exposure_usd"] == 9000.0
        assert a["kind"] == "Bank-account change"
        # bank-account change is high trust-sensitivity → not a blind approve
        assert a["recommended_verdict"] in ("challenge", "block")
    finally:
        _reset()
