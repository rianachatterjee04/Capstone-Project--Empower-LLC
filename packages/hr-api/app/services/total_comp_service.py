"""Unified Total-Compensation service.

Assembles ONE Total-Comp view per employee by pulling EVERY pay stream from its
real source, then folding them with the pure, deterministic aggregator in
`total_comp_core`:

  * base salary + target/actual bonus  -> HR comp_records (effective-dated)
  * benefits value                     -> derived (HR benefits % of base)
  * sales commission earned/accrued    -> packages/api commission engine
                                          (GET /sales-commission/reports/leaderboard,
                                          forwarding the caller's bearer token)
  * payroll gross YTD (actuals)        -> packages/payroll internal seam
                                          (InternalPayrollConnector.pull_ytd_earnings,
                                          X-Internal-Secret)
  * equity granted/vested/unvested/annualized -> HR cap-table + ASC-718 engine

EACH source is fail-soft: if it cannot be reached the component is marked
`available=False` with a human reason and contributes zero — the rest of the
view is still returned.  This service NEVER raises because a downstream is down.

The heavy math lives in the pure core (golden-vector tested); this module is
the I/O shell.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.internal_payroll import InternalPayrollConnector
from app.services import total_comp_core as core

# Benefits are not stored per-employee; HR models them as a % of base (the CFO
# planning default).  Overridable via env for orgs with a different loading.
DEFAULT_BENEFITS_PCT = float(os.getenv("HR_BENEFITS_PCT", "0.22"))


# ---------------------------------------------------------------------------
# Cash (base + bonus) — effective-dated comp_records
# ---------------------------------------------------------------------------
async def _fetch_cash(db: AsyncSession, org_id: str,
                      employee_id: Optional[str], plan_year: int) -> core.CashComp:
    """Latest effective-dated cash comp on/before the end of the plan year.

    Reads base_salary + bonus_target from comp_records (unique per
    org/employee/effective_date).  Benefits are derived as a % of base."""
    if not employee_id:
        return core.CashComp(reason="no employee selected")
    as_of = date(plan_year, 12, 31)
    try:
        row = (await db.execute(text("""
            SELECT base_salary, bonus_target, currency, effective_date
            FROM comp_records
            WHERE org_id = :org AND employee_id = :eid AND effective_date <= :asof
            ORDER BY effective_date DESC LIMIT 1
        """), {"org": org_id, "eid": employee_id, "asof": as_of})).mappings().first()
    except Exception:
        # Fail-soft, but say which failure this was: a missing table is not the
        # same fact as an employee with no comp record, and neither is a salary.
        return core.CashComp(reason="compensation records could not be read")
    if not row:
        return core.CashComp(
            reason=f"no compensation record effective on or before {as_of.isoformat()}")
    base = float(row["base_salary"] or 0)
    return core.CashComp(
        available=True,
        reason=None,
        base_salary=base,
        bonus_target=float(row["bonus_target"] or 0),
        benefits_value=round(base * DEFAULT_BENEFITS_PCT, 2),
        currency=row["currency"] or "USD",
        as_of=row["effective_date"].isoformat() if row["effective_date"] else None,
    )


# ---------------------------------------------------------------------------
# Commission — packages/api commission engine (fail-soft HTTP)
# ---------------------------------------------------------------------------
def _commission_base_url() -> Optional[str]:
    url = os.getenv("COMMISSION_API_URL") or os.getenv("FINANCE_API_URL")
    return url.rstrip("/") if url else None


async def _fetch_commission(employee_id: Optional[str], plan_year: int,
                            bearer_token: Optional[str],
                            transport: Optional[httpx.BaseTransport] = None
                            ) -> core.CommissionComp:
    """Pull the rep's commission (earned YTD, accrued/pending, plan target)
    from packages/api's leaderboard, matched by employee_id.

    The commission API is user-authenticated (licensed bearer JWT), so we
    forward the caller's Authorization header.  Any of {no URL configured, no
    token, service down, non-200, rep not on the leaderboard} -> component
    marked unavailable with the reason.  Never raises."""
    if not employee_id:
        return core.CommissionComp(available=False, reason="no employee id")
    base = _commission_base_url()
    if not base:
        return core.CommissionComp(
            available=False,
            reason="commission API not configured (set COMMISSION_API_URL)")
    if not bearer_token:
        return core.CommissionComp(
            available=False,
            reason="commission API needs an authenticated request; none forwarded")
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        async with httpx.AsyncClient(base_url=base, timeout=5.0,
                                     transport=transport, headers=headers) as client:
            r = await client.get("/sales-commission/reports/leaderboard",
                                 params={"year": plan_year})
    except httpx.HTTPError as exc:
        return core.CommissionComp(available=False,
                                   reason=f"commission service unreachable: {exc!r}")
    if r.status_code != 200:
        return core.CommissionComp(
            available=False,
            reason=f"commission service returned {r.status_code}")
    try:
        rows = (r.json() or {}).get("rows", [])
    except Exception:
        return core.CommissionComp(available=False,
                                   reason="commission response not parseable")
    mine = next((x for x in rows if str(x.get("employee_id")) == str(employee_id)), None)
    if mine is None:
        return core.CommissionComp(
            available=False,
            reason="employee not found on commission plan (not a sales rep?)")
    earned = float(mine.get("commission_ytd") or 0.0)
    paid = float(mine.get("commission_paid") or 0.0)
    # Target commission: the leaderboard exposes quota_annual + (optionally)
    # commission_pct. Target commission = quota × pct when both are present;
    # else fall back to an explicit commission_target field; else 0.0.
    target = 0.0
    if mine.get("commission_target") is not None:
        target = float(mine.get("commission_target") or 0.0)
    elif mine.get("commission_pct") is not None:
        target = float(mine.get("quota_annual") or 0.0) * \
            float(mine.get("commission_pct") or 0.0)
    return core.CommissionComp(
        available=True,
        earned_ytd=earned,
        accrued_pending=max(0.0, earned - paid),
        plan_target=target,
    )


# ---------------------------------------------------------------------------
# Payroll actual (gross YTD) — internal seam
# ---------------------------------------------------------------------------
async def _fetch_payroll_actual(org_id: str, employee_id: Optional[str],
                                plan_year: int,
                                connector: Optional[InternalPayrollConnector] = None
                                ) -> core.PayrollActualComp:
    """Gross earned YTD from packages/payroll via the internal X-Internal-Secret
    seam.  Fail-soft: unreachable / not-synced / no-run-yet -> unavailable."""
    if not employee_id:
        return core.PayrollActualComp(available=False, reason="no employee id")
    conn = connector or InternalPayrollConnector()
    res = await conn.pull_ytd_earnings(org_id, employee_id, year=plan_year)
    if not res.ok:
        return core.PayrollActualComp(
            available=False,
            reason=str(res.details.get("error", "payroll unavailable")))
    ytd = (res.details or {}).get("ytd")
    if not ytd:
        return core.PayrollActualComp(
            available=False,
            reason=str(res.details.get("reason", "no payroll actuals yet")))
    return core.PayrollActualComp(available=True,
                                  gross_ytd=float(ytd.get("gross") or 0.0))


# ---------------------------------------------------------------------------
# Equity — NOT PART OF THIS DEPLOYMENT
#
# The cap-table module (grants, stakeholders, 409A valuations, ASC 718) is not
# included in this build. Total comp already models equity being unavailable —
# core.EquityComp carries `available` and a `reason` — so the answer is the
# honest one rather than a zero that reads like "this employee has no equity".
#
# Cash, benefits, commission and payroll actuals are unaffected.
# ---------------------------------------------------------------------------
EQUITY_UNAVAILABLE_REASON = (
    "cap table is not part of this deployment, so the equity component of "
    "total compensation cannot be computed"
)


async def _fetch_equity(db: AsyncSession, org_id: str,
                        employee_id: Optional[str], plan_year: int,
                        ) -> tuple[core.EquityComp, Optional[float]]:
    return core.EquityComp(available=False,
                           reason=EQUITY_UNAVAILABLE_REASON), None


async def build_total_comp(
    db: AsyncSession, *, org_id: str, employee_id: Optional[str], plan_year: int,
    bearer_token: Optional[str] = None,
    commission_transport: Optional[httpx.BaseTransport] = None,
    payroll_connector: Optional[InternalPayrollConnector] = None,
) -> dict:
    """Assemble the unified Total-Comp payload for one employee.

    Fetches all four streams fail-soft, then folds them deterministically.
    `bearer_token`/`commission_transport`/`payroll_connector` are injection
    seams for the router and for tests."""
    cash = await _fetch_cash(db, org_id, employee_id, plan_year)
    commission = await _fetch_commission(employee_id, plan_year, bearer_token,
                                         transport=commission_transport)
    payroll_actual = await _fetch_payroll_actual(org_id, employee_id, plan_year,
                                                 connector=payroll_connector)
    equity, fmv = await _fetch_equity(db, org_id, employee_id, plan_year)

    return core.assemble_total_comp(
        employee_id=employee_id, plan_year=plan_year, cash=cash,
        commission=commission, payroll_actual=payroll_actual, equity=equity,
        current_fmv=fmv,
    )
