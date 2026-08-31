"""Regression tests for HR document-upload storage isolation.

These lock the tenant-isolation guarantees of POST /api/documents/presign
(app/api/routers/documents.py) — the one code path that hands a client a
Supabase Storage path. They are the app-layer complement to the object-level
RLS added in packages/api/migrations/152_storage_security.sql, so a future
edit that loosens either the path-traversal rejection, the org prefix, the
cross-org employee check, or the server-forced bucket fails CI here.

Proven WITHOUT a live Postgres by overriding the auth + db dependencies:
  * presign rejects category / filename / employee_id containing / \\ .. or NUL
  * the returned path ALWAYS begins with the caller's org_id
  * an employee_id in another org is refused (403)
  * the bucket in the response equals the server default and a client-supplied
    "bucket" in the body cannot override it

Run: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_documents_storage_isolation.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Actor, db_session, require_org
from app.api.entitlements import require_hr_access
from app.core.config import settings
from app.main import app

ORG = "11111111-1111-1111-1111-111111111111"
UID = "22222222-2222-2222-2222-222222222222"
OTHER_EMP = "33333333-3333-3333-3333-333333333333"

PRESIGN = "/api/documents/presign"

# The traversal / injection payloads the endpoint must reject in a path segment.
BAD_SEGMENTS = ["a/b", "a\\b", "..", "../etc", "x\x00y", "..\\..\\win"]


# --------------------------------------------------------------------------- #
# Fake async DB doubles (the endpoint only ever calls db.execute(...).first()) #
# --------------------------------------------------------------------------- #
class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _OwnsDB:
    """Ownership lookup succeeds — the employee belongs to the caller's org."""

    async def execute(self, *a, **k):
        return _Res((1,))


class _NoOwnDB:
    """Ownership lookup returns nothing — the employee is in another org."""

    async def execute(self, *a, **k):
        return _Res(None)


class _ForbidDB:
    """Any DB access is a bug: pure path-segment validation must short-circuit
    before the endpoint ever touches Postgres."""

    async def execute(self, *a, **k):
        raise AssertionError("DB should not be queried for path-segment validation")


def _client(db, role: str = "owner") -> TestClient:
    actor = Actor(user_id=UID, org_id=ORG, role=role, claims={"email": "x@y.z"})
    app.dependency_overrides[require_org] = lambda: actor
    app.dependency_overrides[require_hr_access] = lambda: actor
    app.dependency_overrides[db_session] = lambda: db
    return TestClient(app)


def _reset():
    for dep in (require_org, require_hr_access, db_session):
        app.dependency_overrides.pop(dep, None)


# --------------------------------------------------------------------------- #
# 1. Path-segment rejection (/ \ .. NUL) for category and filename            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", BAD_SEGMENTS)
def test_presign_rejects_bad_category(bad):
    c = _client(_ForbidDB())
    try:
        r = c.post(PRESIGN, json={"category": bad, "filename": "ok.pdf"})
        assert r.status_code == 400, r.text
        assert "category" in r.json()["detail"].lower()
    finally:
        _reset()


@pytest.mark.parametrize("bad", BAD_SEGMENTS)
def test_presign_rejects_bad_filename(bad):
    c = _client(_ForbidDB())
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": bad})
        assert r.status_code == 400, r.text
        assert "filename" in r.json()["detail"].lower()
    finally:
        _reset()


@pytest.mark.parametrize("bad", BAD_SEGMENTS)
def test_presign_rejects_traversal_employee_id_even_if_ownership_matched(bad):
    """Defense in depth: even if the ownership row somehow matched, a traversal
    payload in employee_id is still rejected by _reject_path_segment (400),
    never silently woven into the storage path."""
    c = _client(_OwnsDB())
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": "ok.pdf",
                                  "employee_id": bad})
        assert r.status_code == 400, r.text
        assert "employee_id" in r.json()["detail"].lower()
    finally:
        _reset()


# --------------------------------------------------------------------------- #
# 2. Returned path always begins with the caller's org_id                     #
# --------------------------------------------------------------------------- #
def test_presign_path_is_prefixed_with_caller_org_and_user():
    c = _client(_ForbidDB())  # no employee_id -> no DB call
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": "passport.pdf"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["path"].startswith(f"{ORG}/"), body
        # no employee_id -> targets the caller's own user folder
        assert body["path"] == f"{ORG}/{UID}/i9/passport.pdf"
    finally:
        _reset()


def test_presign_path_prefixed_with_org_for_owned_employee():
    c = _client(_OwnsDB())
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": "passport.pdf",
                                  "employee_id": OTHER_EMP})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["path"].startswith(f"{ORG}/"), body
        assert body["path"] == f"{ORG}/{OTHER_EMP}/i9/passport.pdf"
    finally:
        _reset()


def test_presign_defaults_missing_category_and_filename_under_org_prefix():
    c = _client(_ForbidDB())
    try:
        r = c.post(PRESIGN, json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["path"].startswith(f"{ORG}/{UID}/")
    finally:
        _reset()


# --------------------------------------------------------------------------- #
# 3. Cross-org employee_id is refused                                         #
# --------------------------------------------------------------------------- #
def test_presign_refuses_cross_org_employee():
    c = _client(_NoOwnDB())
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": "ok.pdf",
                                  "employee_id": OTHER_EMP})
        assert r.status_code == 403, r.text
        assert "your org" in r.json()["detail"].lower()
    finally:
        _reset()


# --------------------------------------------------------------------------- #
# 4. Bucket is server-forced and cannot be overridden by the request body     #
# --------------------------------------------------------------------------- #
def test_presign_bucket_is_server_default():
    c = _client(_ForbidDB())
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": "ok.pdf"})
        assert r.status_code == 200, r.text
        assert r.json()["bucket"] == settings.supabase_storage_bucket == "foundry-people"
    finally:
        _reset()


def test_presign_ignores_client_supplied_bucket():
    c = _client(_ForbidDB())
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": "ok.pdf",
                                  "bucket": "attacker-controlled-bucket"})
        assert r.status_code == 200, r.text
        # the client value is ignored entirely; the server default wins
        assert r.json()["bucket"] == "foundry-people"
    finally:
        _reset()


# --------------------------------------------------------------------------- #
# 5. Role gate still applies                                                  #
# --------------------------------------------------------------------------- #
def test_presign_rejects_disallowed_role():
    c = _client(_ForbidDB(), role="viewer")
    try:
        r = c.post(PRESIGN, json={"category": "i9", "filename": "ok.pdf"})
        assert r.status_code == 403, r.text
    finally:
        _reset()
