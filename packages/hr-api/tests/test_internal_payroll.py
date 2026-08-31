"""Unit tests for app/integrations/internal_payroll.py.

No live payroll service needed: httpx.MockTransport is injected into the
connector.  Run: pytest test_internal_payroll.py
(only needs httpx + pytest; the module imports app.integrations.* only).
"""
from __future__ import annotations

import asyncio
import json

import httpx

import uuid as _uuid
from datetime import date as _date

from app.integrations.internal_payroll import (InternalPayrollConnector,
                                               load_current_comp,
                                               map_hr_employee,
                                               resolve_comp_fields)

ORG = "cccccccc-cccc-cccc-cccc-cccccccccccc"


class FakeEmp:
    def __init__(self, id, legal_name, email, department=None, status="active",
                 location=None):
        self.id = id
        self.legal_name = legal_name
        self.email = email
        self.department = department
        self.status = status
        self.location = location


def _connector(handler) -> InternalPayrollConnector:
    return InternalPayrollConnector(
        config={"base_url": "http://payroll.test", "secret": "s3cret"},
        transport=httpx.MockTransport(handler))


# -------------------------------------------------------------------------
def test_map_hr_employee_fields():
    emp = FakeEmp("e-1", "Ada Mae Lovelace", "ada@x.test", department="eng")
    m = map_hr_employee(emp)
    assert m["hr_employee_id"] == "e-1"
    assert m["first_name"] == "Ada Mae" and m["last_name"] == "Lovelace"
    assert m["email"] == "ada@x.test" and m["department"] == "eng"
    assert "cost_center" not in m          # absent on hr-api Employee -> omitted
    assert m["status"] == "active"
    # single-token name + terminated status
    m2 = map_hr_employee(FakeEmp("e-2", "Cher", "cher@x.test", status="terminated"))
    assert m2["first_name"] == "Cher" and m2["last_name"] == ""
    assert m2["status"] == "terminated"
    # cost_center included when the source object has one
    emp3 = FakeEmp("e-3", "Bo Ba", "bo@x.test")
    emp3.cost_center = "CC-9"
    assert map_hr_employee(emp3)["cost_center"] == "CC-9"


# -------------------------------------------------------------------------
def test_push_employees_success_and_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["secret"] = request.headers.get("X-Internal-Secret")
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={
            "org_id": ORG, "created": 1, "updated": 1, "unchanged": 0,
            "error": 0, "results": [
                {"hr_employee_id": "e-1", "employee_id": "p-1", "action": "created"},
                {"hr_employee_id": "e-2", "employee_id": "p-2", "action": "updated"},
            ]})

    c = _connector(handler)
    res = asyncio.run(c.push_employees(ORG, [
        map_hr_employee(FakeEmp("e-1", "Ada Lovelace", "ada@x.test")),
        map_hr_employee(FakeEmp("e-2", "Bob B", "bob@x.test")),
    ]))
    assert res.ok is True
    assert res.details["synced"] == 2
    assert len(res.details["results"]) == 2
    assert seen["path"] == "/api/payroll/internal/employees/upsert"
    assert seen["secret"] == "s3cret"
    assert seen["body"]["org_id"] == ORG
    assert seen["body"]["employees"][0]["hr_employee_id"] == "e-1"


def test_push_employees_license_locked_402_fail_soft():
    def handler(request):
        return httpx.Response(402, json={
            "detail": {"feature": "payroll",
                       "error": "payroll module is not activated for this org"}})
    res = asyncio.run(_connector(handler).push_employees(
        ORG, [{"hr_employee_id": "e-1", "first_name": "A", "last_name": "B",
               "email": "a@b.c"}]))
    assert res.ok is False
    assert res.details["synced"] == 0
    assert res.details["status_code"] == 402
    assert "402" in res.details["error"]


def test_push_employees_unreachable_fail_soft():
    def handler(request):
        raise httpx.ConnectError("connection refused")
    res = asyncio.run(_connector(handler).push_employees(
        ORG, [{"hr_employee_id": "e-1", "email": "a@b.c"}]))
    assert res.ok is False and res.details["synced"] == 0
    assert "unreachable" in res.details["error"]
    # empty push short-circuits (no request, still ok)
    res2 = asyncio.run(_connector(handler).push_employees(ORG, []))
    assert res2.ok is True and res2.details["synced"] == 0


# -------------------------------------------------------------------------
def test_push_timesheets_payload_and_synced_count():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={
            "org_id": ORG, "stored": [{"hr_employee_id": "e-1"}],
            "skipped": [], "superseded": 0})

    res = asyncio.run(_connector(handler).push_timesheets(
        ORG, "2025-01-01", "2025-01-15",
        [{"hr_employee_id": "e-1",
          "hours_by_type": {"regular": 80, "overtime": 5}}]))
    assert res.ok is True and res.details["synced"] == 1
    assert seen["path"] == "/api/payroll/internal/timesheets"
    assert seen["body"]["period_start"] == "2025-01-01"
    assert seen["body"]["entries"][0]["hours_by_type"]["overtime"] == 5


def test_test_connection():
    ok = asyncio.run(_connector(
        lambda req: httpx.Response(200, json={"ok": True})).test_connection())
    assert ok is True

    def down(request):
        raise httpx.ConnectError("nope")
    assert asyncio.run(_connector(down).test_connection()) is False


# -------------------------------------------------------------------------
# pull_ytd_earnings — the READ seam used by Total-Comp for payroll actuals
# -------------------------------------------------------------------------
def test_pull_ytd_earnings_success():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["secret"] = request.headers.get("X-Internal-Secret")
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={
            "org_id": ORG, "hr_employee_id": "e-1", "year": 2026,
            "ytd": {"gross": 95000.0, "net": 71000.0}})

    res = asyncio.run(_connector(handler).pull_ytd_earnings(ORG, "e-1", year=2026))
    assert res.ok is True
    assert res.details["ytd"]["gross"] == 95000.0
    assert seen["path"] == "/api/payroll/internal/employees/e-1/ytd"
    assert seen["secret"] == "s3cret"
    assert seen["query"]["org_id"] == ORG
    assert seen["query"]["year"] == "2026"


def test_pull_ytd_earnings_not_synced_returns_null_ytd():
    def handler(request):
        return httpx.Response(200, json={
            "org_id": ORG, "hr_employee_id": "e-1", "year": 2026,
            "ytd": None, "reason": "employee not synced to payroll"})
    res = asyncio.run(_connector(handler).pull_ytd_earnings(ORG, "e-1"))
    assert res.ok is True
    assert res.details["ytd"] is None
    assert res.details["reason"] == "employee not synced to payroll"


def test_pull_ytd_earnings_unreachable_fail_soft():
    def handler(request):
        raise httpx.ConnectError("connection refused")
    res = asyncio.run(_connector(handler).pull_ytd_earnings(ORG, "e-1"))
    assert res.ok is False
    assert "unreachable" in res.details["error"]


def test_pull_ytd_earnings_402_license_fail_soft():
    def handler(request):
        return httpx.Response(402, json={"detail": {"feature": "payroll"}})
    res = asyncio.run(_connector(handler).pull_ytd_earnings(ORG, "e-1"))
    assert res.ok is False
    assert res.details["status_code"] == 402


# -------------------------------------------------------------------------
# P0-1: comp resolver + comp/schedule enrichment in the payroll push
# -------------------------------------------------------------------------
def test_resolve_comp_fields_salary_and_hourly():
    # HR "salary" basis carries an ANNUAL amount -> payroll annual basis.
    salary = resolve_comp_fields({"basis": "salary", "amount": 120000})
    assert salary == {"pay_basis": "annual", "basis_amount_cents": 12_000_000}
    # HR "hourly" -> hourly rate in cents + a default_hours_per_period fallback.
    hourly = resolve_comp_fields({"basis": "hourly", "amount": 42.50})
    assert hourly["pay_basis"] == "hourly"
    assert hourly["basis_amount_cents"] == 4250
    assert hourly["default_hours_per_period"] == 80.0
    # default basis is salary/annual when unspecified
    assert resolve_comp_fields({"amount": 90000})["pay_basis"] == "annual"


def test_resolve_comp_fields_absent_or_zero_is_empty():
    assert resolve_comp_fields(None) == {}
    assert resolve_comp_fields({"basis": "salary", "amount": None}) == {}
    assert resolve_comp_fields({"basis": "salary", "amount": 0}) == {}
    # works off duck-typed objects too, not just dicts

    class _Comp:
        basis = "hourly"
        amount = 30
    assert resolve_comp_fields(_Comp())["basis_amount_cents"] == 3000


def test_map_hr_employee_emits_comp_schedule_and_work_state():
    emp = FakeEmp("e-1", "Ada Lovelace", "ada@x.test", department="eng",
                  location="Austin, TX")
    m = map_hr_employee(
        emp,
        comp={"basis": "annual", "amount": 150000},
        schedule_id="sched-123")
    # comp -> pay basis + amount
    assert m["pay_basis"] == "annual"
    assert m["basis_amount_cents"] == 15_000_000
    # work state parsed from free-text location
    assert m["work_state"] == "TX"
    # payroll-eligible (has comp) -> default pay method emitted
    assert m["pay_method"] == "direct_deposit"
    # explicit per-employee schedule wins
    assert m["schedule_id"] == "sched-123"


def test_map_hr_employee_schedule_default_and_no_comp_omits_fields():
    emp = FakeEmp("e-2", "Bo Ba", "bo@x.test", location="Remote")
    # no comp, no explicit schedule -> falls back to org default schedule;
    # comp fields + pay_method omitted so the upsert never clears stored comp.
    m = map_hr_employee(emp, default_schedule_id="org-default-sched")
    assert m["schedule_id"] == "org-default-sched"
    assert "pay_basis" not in m
    assert "basis_amount_cents" not in m
    assert "pay_method" not in m           # not payroll-eligible yet
    assert "work_state" not in m           # "Remote" is not a state code
    # hourly comp attaches the default-hours fallback + DD pay method
    m2 = map_hr_employee(emp, comp={"basis": "hourly", "amount": 25})
    assert m2["pay_basis"] == "hourly" and m2["default_hours_per_period"] == 80.0
    assert m2["pay_method"] == "direct_deposit"


class _CompRow:
    def __init__(self, org, eid, eff, end):
        self.org_id = org
        self.employee_id = eid
        self.effective_date = eff
        self.end_date = end


def _fake_comp_db(rows):
    class _Scalars:
        def all(self):
            return rows

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Db:
        async def execute(self, _stmt):
            return _Result()

    return _Db()


def test_load_current_comp_picks_current_effective_row():
    org = str(_uuid.uuid4())
    e1 = str(_uuid.uuid4())
    rows = [
        _CompRow(org, e1, _date(2025, 1, 1), _date(2025, 12, 31)),   # closed
        _CompRow(org, e1, _date(2026, 1, 1), None),                  # open/current
    ]
    out = asyncio.run(load_current_comp(
        _fake_comp_db(rows), org, [e1], as_of=_date(2026, 6, 1)))
    assert out[e1].effective_date == _date(2026, 1, 1)   # the in-force row wins


def test_load_current_comp_empty_and_bad_input():
    org = str(_uuid.uuid4())
    assert asyncio.run(load_current_comp(_fake_comp_db([]), org, [])) == {}
    # non-UUID org id fails soft to {} (never raises into the sync path)
    assert asyncio.run(load_current_comp(_fake_comp_db([]), "not-a-uuid", ["x"])) == {}
