"""Golden-vector tests for Total Compensation Unification.

DB-free: exercises the pure aggregator (app.services.total_comp_core) with
hand-checked vectors, plus the fail-soft fetch paths of
app.services.total_comp_service using httpx.MockTransport and a fake payroll
connector.  No live commission/payroll/DB service required.

Run:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_total_comp.py -q
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services import total_comp_core as core
from app.services import total_comp_service as svc
from app.models.compensation_module import TotalCompensation


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _run(coro):
    return asyncio.run(coro)


def _assemble(**kw):
    base = dict(
        employee_id="e-1", plan_year=2026,
        cash=core.CashComp(base_salary=120_000, bonus_target=20_000,
                           benefits_value=15_000, currency="USD"),
        commission=core.CommissionComp(available=True, earned_ytd=40_000,
                                       accrued_pending=8_000, plan_target=35_000),
        payroll_actual=core.PayrollActualComp(available=True, gross_ytd=95_000),
        equity=core.EquityComp(available=True, grant_value=120_000,
                               vested_value=45_000, unvested_value=75_000,
                               annualized=30_000),
    )
    base.update(kw)
    return core.assemble_total_comp(**base)


# ===========================================================================
# 1. Worked example from the spec — the headline golden vector
# ===========================================================================
def test_worked_example_target_and_actual():
    # base 120k + bonus 20k + benefits 15k + commission earned 40k/accrued 8k
    # + commission target 35k + equity annualized 30k.
    p = _assemble()
    # target = 120 + 20 + 15 + 35 (commission target) + 30 (equity) = 220k
    assert p["totals"]["target_total_comp"] == 220_000.00
    # actual = 120 + 20 (bonus actual==target) + 15 + 40 (earned) + 30 = 225k
    assert p["totals"]["actual_total_comp"] == 225_000.00
    # variance actual-target = +5k (rep is ahead of plan)
    assert p["totals"]["variance_to_target"] == 5_000.00


def test_worked_example_attainment_pct():
    p = _assemble()
    # 225000 / 220000 * 100 = 102.3%
    assert p["totals"]["attainment_pct"] == 102.3


# ===========================================================================
# 2. Aggregation totals — base+bonus+benefits+commission+equity
# ===========================================================================
def test_all_five_components_sum_into_target():
    p = _assemble(
        cash=core.CashComp(base_salary=100_000, bonus_target=10_000,
                           benefits_value=22_000),
        commission=core.CommissionComp(available=True, earned_ytd=0,
                                       accrued_pending=0, plan_target=25_000),
        equity=core.EquityComp(available=True, annualized=13_000),
    )
    assert p["totals"]["target_total_comp"] == 100_000 + 10_000 + 22_000 + 25_000 + 13_000


def test_actual_uses_earned_not_target_commission():
    p = _assemble(
        commission=core.CommissionComp(available=True, earned_ytd=12_500,
                                       accrued_pending=2_500, plan_target=40_000),
    )
    # actual commission slice is EARNED (12.5k), not target.
    # actual = 120 + 20 + 15 + 12.5 + 30 = 197.5k
    assert p["totals"]["actual_total_comp"] == 197_500.00


# ===========================================================================
# 3. Mix percentages sum to exactly 100
# ===========================================================================
def test_mix_sums_to_100():
    p = _assemble()
    mix = p["totals"]["mix_pct_by_component"]
    assert round(sum(mix.values()), 2) == 100.00


def test_mix_components_present_and_proportional():
    p = _assemble()
    mix = p["totals"]["mix_pct_by_component"]
    # target = 220k; base 120k -> ~54.55%
    assert set(mix) == {"base_salary", "bonus", "benefits", "commission", "equity"}
    assert abs(mix["base_salary"] - round(120_000 / 220_000 * 100, 2)) <= 0.05


def test_mix_empty_when_no_target():
    p = _assemble(
        cash=core.CashComp(),  # all zero
        commission=core.CommissionComp(available=False),
        equity=core.EquityComp(available=False),
        payroll_actual=core.PayrollActualComp(available=False),
    )
    assert p["totals"]["target_total_comp"] == 0.0
    assert p["totals"]["mix_pct_by_component"] == {}
    assert p["totals"]["attainment_pct"] is None


# ===========================================================================
# 4. Commission earned + accrued split
# ===========================================================================
def test_commission_earned_accrued_split_surfaced():
    p = _assemble()
    c = p["commission"]
    assert c["available"] is True
    assert c["earned_ytd"] == 40_000.00
    assert c["accrued_pending"] == 8_000.00
    assert c["plan_target"] == 35_000.00


# ===========================================================================
# 5. Equity vested / unvested / annualized split
# ===========================================================================
def test_equity_vested_unvested_annualized_split():
    p = _assemble()
    e = p["equity"]
    assert e["available"] is True
    assert e["vested_value"] == 45_000.00
    assert e["unvested_value"] == 75_000.00
    assert e["annualized"] == 30_000.00
    assert e["grant_value"] == 120_000.00
    # only the ANNUALIZED slice is in the target total, not vested/unvested.
    assert p["totals"]["target_total_comp"] == 220_000.00


# ===========================================================================
# 6. Bonus actual overrides target when provided
# ===========================================================================
def test_bonus_actual_override():
    p = _assemble(
        cash=core.CashComp(base_salary=120_000, bonus_target=20_000,
                           bonus_actual=5_000, benefits_value=15_000),
    )
    # actual uses bonus_actual=5k: 120 + 5 + 15 + 40 (earned) + 30 = 210k
    assert p["totals"]["actual_total_comp"] == 210_000.00
    # target still uses bonus_target=20k
    assert p["totals"]["target_total_comp"] == 220_000.00
    assert p["bonus"] == {"target": 20_000.00, "actual": 5_000.00}


# ===========================================================================
# 7. FAIL-SOFT: commission unavailable -> zeroed, total still returned
# ===========================================================================
def test_failsoft_commission_unavailable():
    p = _assemble(
        commission=core.CommissionComp(available=False,
                                       reason="commission service unreachable"),
    )
    assert p["commission"]["available"] is False
    assert p["commission"]["reason"] == "commission service unreachable"
    # target drops the 35k commission slice: 120+20+15+30 = 185k
    assert p["totals"]["target_total_comp"] == 185_000.00
    # actual drops earned commission: 120+20+15+30 = 185k
    assert p["totals"]["actual_total_comp"] == 185_000.00
    # mix still sums to 100 over the remaining components
    assert round(sum(p["totals"]["mix_pct_by_component"].values()), 2) == 100.00
    assert "commission" not in p["totals"]["mix_pct_by_component"]


# ===========================================================================
# 8. FAIL-SOFT: payroll unavailable -> flagged, rest intact
# ===========================================================================
def test_failsoft_payroll_unavailable():
    p = _assemble(
        payroll_actual=core.PayrollActualComp(available=False,
                                              reason="payroll not synced"),
    )
    assert p["payroll_actual"]["available"] is False
    assert p["payroll_actual"]["source"] == "unavailable"
    assert p["payroll_actual"]["gross_ytd"] == 0.0
    # payroll never contributes to the totals anyway (reconciliation only)
    assert p["totals"]["target_total_comp"] == 220_000.00


def test_payroll_available_source_label():
    p = _assemble()
    assert p["payroll_actual"]["available"] is True
    assert p["payroll_actual"]["source"] == "payroll"
    assert p["payroll_actual"]["gross_ytd"] == 95_000.00


# ===========================================================================
# 9. FAIL-SOFT: equity absent -> zeroed, cash-only total
# ===========================================================================
def test_failsoft_equity_absent():
    p = _assemble(
        equity=core.EquityComp(available=False, reason="no equity grants"),
    )
    assert p["equity"]["available"] is False
    # target = 120+20+15+35 (commission) = 190k, no equity
    assert p["totals"]["target_total_comp"] == 190_000.00
    assert "equity" not in p["totals"]["mix_pct_by_component"]


# ===========================================================================
# 10. FAIL-SOFT: all external sources down -> cash+benefits only, no crash
# ===========================================================================
def test_failsoft_all_external_down():
    p = _assemble(
        commission=core.CommissionComp(available=False, reason="down"),
        payroll_actual=core.PayrollActualComp(available=False, reason="down"),
        equity=core.EquityComp(available=False, reason="down"),
    )
    # only base+bonus+benefits: 120+20+15 = 155k
    assert p["totals"]["target_total_comp"] == 155_000.00
    assert p["totals"]["actual_total_comp"] == 155_000.00
    assert round(sum(p["totals"]["mix_pct_by_component"].values()), 2) == 100.00


# ===========================================================================
# 11. Determinism — identical inputs, identical output
# ===========================================================================
def test_determinism():
    assert _assemble() == _assemble()


# ===========================================================================
# 12. Rounding is to cents and stable
# ===========================================================================
def test_rounding_to_cents():
    p = _assemble(
        cash=core.CashComp(base_salary=100_000.005, bonus_target=0,
                           benefits_value=0),
        commission=core.CommissionComp(available=False),
        equity=core.EquityComp(available=False),
    )
    assert p["base_salary"] == 100_000.01 or p["base_salary"] == 100_000.0


# ===========================================================================
# 13. SERVICE fail-soft: commission not configured -> unavailable
# ===========================================================================
def test_service_commission_no_config(monkeypatch):
    monkeypatch.delenv("COMMISSION_API_URL", raising=False)
    monkeypatch.delenv("FINANCE_API_URL", raising=False)
    c = _run(svc._fetch_commission("e-1", 2026, bearer_token="tok"))
    assert c.available is False
    assert "not configured" in c.reason


# ===========================================================================
# 14. SERVICE fail-soft: commission service returns 200 with rep found
# ===========================================================================
def test_service_commission_found(monkeypatch):
    monkeypatch.setenv("COMMISSION_API_URL", "http://commission.test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer tok"
        return httpx.Response(200, json={"year": 2026, "rows": [
            {"employee_id": "e-1", "commission_ytd": 40_000, "commission_paid": 32_000,
             "quota_annual": 500_000, "commission_pct": 0.07},
            {"employee_id": "e-2", "commission_ytd": 10_000, "commission_paid": 10_000},
        ]})

    c = _run(svc._fetch_commission("e-1", 2026, bearer_token="tok",
                                   transport=httpx.MockTransport(handler)))
    assert c.available is True
    assert c.earned_ytd == 40_000
    assert c.accrued_pending == 8_000            # 40k earned - 32k paid
    assert c.plan_target == 500_000 * 0.07       # quota × pct = 35k


def test_service_commission_rep_not_on_plan(monkeypatch):
    monkeypatch.setenv("COMMISSION_API_URL", "http://commission.test")

    def handler(request):
        return httpx.Response(200, json={"rows": [{"employee_id": "someone-else"}]})

    c = _run(svc._fetch_commission("e-1", 2026, bearer_token="tok",
                                   transport=httpx.MockTransport(handler)))
    assert c.available is False
    assert "not found on commission plan" in c.reason


def test_service_commission_service_down(monkeypatch):
    monkeypatch.setenv("COMMISSION_API_URL", "http://commission.test")

    def handler(request):
        raise httpx.ConnectError("refused")

    c = _run(svc._fetch_commission("e-1", 2026, bearer_token="tok",
                                   transport=httpx.MockTransport(handler)))
    assert c.available is False
    assert "unreachable" in c.reason


# ===========================================================================
# 15. SERVICE fail-soft: payroll actual via fake connector
# ===========================================================================
class _FakePayroll:
    def __init__(self, result):
        self._result = result

    async def pull_ytd_earnings(self, org_id, hr_employee_id, year=None):
        return self._result


def test_service_payroll_available():
    from app.integrations.base import SyncResult
    res = SyncResult(ok=True, details={"ytd": {"gross": 95_000.0}})
    p = _run(svc._fetch_payroll_actual("org", "e-1", 2026,
                                       connector=_FakePayroll(res)))
    assert p.available is True
    assert p.gross_ytd == 95_000.0


def test_service_payroll_not_synced():
    from app.integrations.base import SyncResult
    res = SyncResult(ok=True, details={"ytd": None, "reason": "employee not synced to payroll"})
    p = _run(svc._fetch_payroll_actual("org", "e-1", 2026,
                                       connector=_FakePayroll(res)))
    assert p.available is False
    assert "not synced" in p.reason


def test_service_payroll_unreachable():
    from app.integrations.base import SyncResult
    res = SyncResult(ok=False, details={"error": "payroll unreachable: ConnectError"})
    p = _run(svc._fetch_payroll_actual("org", "e-1", 2026,
                                       connector=_FakePayroll(res)))
    assert p.available is False
    assert "unreachable" in p.reason


# ===========================================================================
# 16. Legacy TotalCompensation still works + unified_summary delegates to core
# ===========================================================================
def test_legacy_class_backward_compatible():
    tc = TotalCompensation(salary=100_000, bonus=10_000,
                           equity_value=30_000, benefits_value=20_000)
    assert tc.total_comp() == 160_000
    s = tc.comp_summary()
    assert s["Total"] == 160_000


def test_legacy_unified_summary_matches_core():
    tc = TotalCompensation(salary=120_000, bonus=20_000,
                           equity_value=30_000, benefits_value=15_000)
    p = tc.unified_summary(
        plan_year=2026, commission_earned_ytd=40_000, commission_accrued=8_000,
        commission_target=35_000, commission_available=True,
        equity_annualized=30_000)
    assert p["totals"]["target_total_comp"] == 220_000.00
    assert p["totals"]["actual_total_comp"] == 225_000.00
