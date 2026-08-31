"""Connector to the in-house Fintra Payroll service (packages/payroll).

HR is the source of truth for PEOPLE: this connector PUSHES employees and
timesheet hours into payroll's internal sync seam
(/api/payroll/internal/* on PAYROLL_API_URL, default http://localhost:8050)
authenticated with the shared X-Internal-Secret header
(PAYROLL_INTERNAL_SECRET, dev default 'dev-internal-secret').

Fail-soft by design: any transport error or non-2xx response becomes
SyncResult(ok=False, details={"synced": 0, "error": ...}) — callers never
crash because payroll is down or the payroll license is not activated
(402 is surfaced in the error detail).

`transport` is injectable so unit tests can use httpx.MockTransport
without a live payroll service.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from app.integrations.base import PayrollConnector, SyncResult

DEFAULT_BASE_URL = "http://localhost:8050"
DEFAULT_SECRET = "dev-internal-secret"

# Hourly fallback hours when no timesheet override exists. Payroll drafts REG
# from the employee's default_hours_per_period; 80 = a standard semimonthly /
# biweekly baseline. Salaried employees are period-paid and ignore this.
DEFAULT_HOURS_PER_PERIOD = 80.0

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}


def _work_state_from_location(location: Any) -> Optional[str]:
    """Best-effort 2-letter work state from HR's free-text `location` string.

    HR stores location as free text (e.g. "TX", "Austin, TX", "Remote — CA").
    Payroll needs a 2-letter USPS code to resolve state income tax; when we
    cannot confidently extract one we return None (payroll simply computes no
    SIT — the run is not blocked). Recognizes a bare code or a trailing
    ", ST" token; never guesses from a city name.
    """
    if not location:
        return None
    text = str(location).strip()
    if not text:
        return None
    # trailing token after the last comma/dash, else the whole string
    import re
    tail = re.split(r"[,\-–—]", text)[-1].strip().upper()
    if tail in _US_STATES:
        return tail
    whole = text.strip().upper()
    if whole in _US_STATES:
        return whole
    return None


def _attr(obj: Any, name: str) -> Any:
    """Read `name` from an object attr or a dict key (comp rows may be either)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def resolve_comp_fields(comp: Any) -> Dict[str, Any]:
    """Map an HR comp_history record (the CURRENT effective row) to payroll
    comp fields: {pay_basis, basis_amount_cents[, default_hours_per_period]}.

    `comp` is a CompHistory ORM row / duck-typed object / dict with `basis`
    ('salary'|'hourly') and `amount` (whole currency). Returns {} when comp is
    absent or has no usable amount, so map_hr_employee omits the fields and the
    payroll upsert leaves the employee's stored comp untouched.

    Basis mapping (aligned with payroll's ANNUALIZE + hourly handling):
      salary -> pay_basis='annual', basis_amount_cents = annual salary in cents
      hourly -> pay_basis='hourly', basis_amount_cents = hourly rate in cents
                + a default_hours_per_period fallback for run drafting.
    """
    if comp is None:
        return {}
    amount = _attr(comp, "amount")
    if amount is None:
        return {}
    try:
        cents = int(round(float(amount) * 100))
    except (TypeError, ValueError):
        return {}
    if cents <= 0:
        return {}
    basis = (_attr(comp, "basis") or "salary")
    if basis == "hourly":
        return {"pay_basis": "hourly", "basis_amount_cents": cents,
                "default_hours_per_period": DEFAULT_HOURS_PER_PERIOD}
    # "salary" (HR's annual-salary convention) and any unknown basis annualize.
    return {"pay_basis": "annual", "basis_amount_cents": cents}


async def load_current_comp(db: Any, org_id: str,
                            employee_ids: List[str],
                            as_of: Any = None) -> Dict[str, Any]:
    """Load each employee's CURRENT effective comp_history row.

    Returns {str(employee_id): CompHistory} for employees that have a comp row
    in force on `as_of` (default today). Used by the HR->payroll sync to enrich
    map_hr_employee with pay_basis/amount. Imports the DB layer lazily so the
    connector module stays importable without the full app stack (the unit
    tests import app.integrations.* only).
    """
    import uuid as _uuid
    from datetime import date as _date

    from sqlalchemy import select as _select

    from app.db.models import CompHistory
    from app.services.effective_dating import resolve_as_of

    if not employee_ids:
        return {}
    as_of = as_of or _date.today()
    try:
        org_uuid = _uuid.UUID(str(org_id))
        emp_uuids = [_uuid.UUID(str(e)) for e in employee_ids]
    except (TypeError, ValueError):
        return {}

    rows = (await db.execute(_select(CompHistory).where(
        CompHistory.org_id == org_uuid,
        CompHistory.employee_id.in_(emp_uuids)))).scalars().all()

    by_emp: Dict[str, list] = {}
    for r in rows:
        by_emp.setdefault(str(r.employee_id), []).append(
            {"effective_date": r.effective_date, "end_date": r.end_date, "_row": r})

    out: Dict[str, Any] = {}
    for emp_id, recs in by_emp.items():
        current = resolve_as_of(recs, as_of)
        if current is not None:
            out[emp_id] = current["_row"]
    return out


def map_hr_employee(emp: Any, comp: Any = None,
                    schedule_id: Optional[str] = None,
                    default_schedule_id: Optional[str] = None) -> Dict[str, Any]:
    """Map an hr-api Employee row (or duck-typed object) to the payroll
    internal-upsert payload.

    People fields (name/email/department/cost_center) come off the employee;
    SSN/bank are intentionally NOT mapped (payroll owns them and the seam never
    blanks stored values anyway).

    Compensation + payroll-eligibility fields close the hire->comp->pay-run
    loop and are only emitted when derivable (None values are dropped, so the
    upsert never clears a stored payroll value):
      * pay_basis / basis_amount_cents / default_hours_per_period — from the
        employee's CURRENT effective comp_history row (`comp`, resolved by
        load_current_comp); see resolve_comp_fields.
      * work_state — best-effort from HR's free-text location.
      * pay_method — HR does not own bank details; defaults to direct_deposit
        for payroll-eligible (has-comp) employees, overridable via emp.pay_method.
      * schedule_id — explicit per-employee override wins, else emp.schedule_id,
        else the org's default PaySchedule (`default_schedule_id`). Without a
        schedule the employee is synced but EXCLUDED from runs
        (payrun_service.calculate_run filters on schedule_id).
    """
    legal_name = (getattr(emp, "legal_name", None) or "").strip()
    first, _, last = legal_name.rpartition(" ")
    if not first:  # single-token name
        first, last = legal_name, ""
    payload: Dict[str, Any] = {
        "hr_employee_id": str(getattr(emp, "id")),
        "first_name": first or legal_name,
        "last_name": last,
        "email": getattr(emp, "email", None),
        "department": getattr(emp, "department", None),
        "cost_center": getattr(emp, "cost_center", None),
    }
    status = getattr(emp, "status", None)
    if status:
        # payroll only distinguishes active/terminated; HR onboarding states
        # (invited/pending_onboarding/...) sync as active payroll records.
        payload["status"] = "terminated" if status in ("terminated", "offboarded") else "active"

    # work location -> work state (payroll SIT resolution)
    payload["work_state"] = (getattr(emp, "work_state", None)
                             or _work_state_from_location(getattr(emp, "location", None)))

    # compensation (current-effective) -> pay basis + amount
    comp_fields = resolve_comp_fields(comp)
    payload.update(comp_fields)

    # pay method: default DD for payroll-eligible employees, else honor an attr
    pay_method = getattr(emp, "pay_method", None)
    if comp_fields:
        payload["pay_method"] = pay_method or "direct_deposit"
    elif pay_method:
        payload["pay_method"] = pay_method

    # pay schedule: explicit override > employee attr > org default
    payload["schedule_id"] = (schedule_id
                              or getattr(emp, "schedule_id", None)
                              or default_schedule_id)

    return {k: v for k, v in payload.items() if v is not None}


class InternalPayrollConnector(PayrollConnector):
    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 transport: Optional[httpx.BaseTransport] = None):
        cfg = config or {}
        self.base_url = (cfg.get("base_url")
                         or os.getenv("PAYROLL_API_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.secret = (cfg.get("secret")
                       or os.getenv("PAYROLL_INTERNAL_SECRET")
                       or DEFAULT_SECRET)
        self.timeout = float(cfg.get("timeout") or 5.0)
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout,
            transport=self._transport,
            headers={"X-Internal-Secret": self.secret})

    async def _post(self, path: str, payload: dict) -> SyncResult:
        try:
            async with self._client() as client:
                r = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            return SyncResult(ok=False, details={
                "synced": 0, "error": f"payroll unreachable: {exc!r}",
                "payroll_url": self.base_url})
        if r.status_code not in (200, 201):
            detail: Any
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:500]
            return SyncResult(ok=False, details={
                "synced": 0, "error": f"payroll returned {r.status_code}",
                "status_code": r.status_code, "detail": detail})
        return SyncResult(ok=True, details=r.json())

    async def _get(self, path: str, params: dict) -> SyncResult:
        try:
            async with self._client() as client:
                r = await client.get(path, params=params)
        except httpx.HTTPError as exc:
            return SyncResult(ok=False, details={
                "error": f"payroll unreachable: {exc!r}",
                "payroll_url": self.base_url})
        if r.status_code != 200:
            detail: Any
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:500]
            return SyncResult(ok=False, details={
                "error": f"payroll returned {r.status_code}",
                "status_code": r.status_code, "detail": detail})
        return SyncResult(ok=True, details=r.json())

    # ---- PayrollConnector interface -------------------------------------
    async def test_connection(self) -> bool:
        try:
            async with self._client() as client:
                r = await client.get("/healthz")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def pull_employees(self) -> List[Dict[str, Any]]:
        # HR is the source of truth for people; this connector only pushes.
        return []

    async def push_compensation_event(self, event: Dict[str, Any]) -> SyncResult:
        """A compensation change is just an employee upsert on this seam
        (payroll recalculates from the employee record; there is no separate
        comp-event endpoint)."""
        org_id = event.get("org_id")
        employee = event.get("employee")
        if not org_id or not employee:
            return SyncResult(ok=False, details={
                "synced": 0,
                "error": "push_compensation_event requires {org_id, employee}"})
        return await self.push_employees(org_id, [employee])

    # ---- seam-specific pushes -------------------------------------------
    async def push_employees(self, org_id: str,
                             employees: List[Dict[str, Any]]) -> SyncResult:
        if not employees:
            return SyncResult(ok=True, details={"synced": 0, "results": [],
                                                "note": "nothing to sync"})
        res = await self._post("/api/payroll/internal/employees/upsert",
                               {"org_id": org_id, "employees": employees})
        if res.ok:
            body = res.details
            body["synced"] = (body.get("created", 0) + body.get("updated", 0)
                              + body.get("unchanged", 0))
        return res

    async def pull_ytd_earnings(self, org_id: str, hr_employee_id: str,
                                year: Optional[int] = None) -> SyncResult:
        """Read an employee's PAYROLL ACTUALS (gross earned YTD) from the
        payroll internal seam, keyed by the HR employee id.

        Fail-soft like the rest of this connector: transport error or non-200
        -> SyncResult(ok=False, ...); a synced-but-not-yet-paid employee comes
        back ok=True with details['ytd'] is None (payroll returns 200 + null).
        Callers should treat both ok=False and ytd=None as 'payroll actual
        unavailable' and fall back to the rest of the total-comp view."""
        params: Dict[str, Any] = {"org_id": org_id}
        if year is not None:
            params["year"] = year
        return await self._get(
            f"/api/payroll/internal/employees/{hr_employee_id}/ytd", params)

    async def push_timesheets(self, org_id: str, period_start: str,
                              period_end: str,
                              entries: List[Dict[str, Any]]) -> SyncResult:
        if not entries:
            return SyncResult(ok=True, details={"synced": 0, "stored": [],
                                                "note": "nothing to sync"})
        res = await self._post("/api/payroll/internal/timesheets", {
            "org_id": org_id, "period_start": period_start,
            "period_end": period_end, "entries": entries})
        if res.ok:
            res.details["synced"] = len(res.details.get("stored", []))
        return res
