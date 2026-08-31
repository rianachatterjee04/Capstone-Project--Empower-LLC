"""
"No compensation record" and "paid nothing" are different facts.

WHY THIS IS A TEST
CommissionComp and PayrollActualComp both carry `available` and `reason`, which
is why /app/comp could say "unavailable — commission API not configured (set
COMMISSION_API_URL)" and "unavailable — employee not synced to payroll".

CashComp carried neither. For an employee with no comp_records row the same
panel printed "Base salary $0", "Bonus $0 / $0", "Benefits $0" — three lines
asserting what someone is paid, sitting directly beside three that honestly
admitted they knew nothing. It then summed all of it into "Target total comp
$0" in the largest type on the screen.

A sum over four unavailable streams is not zero compensation.
"""
from __future__ import annotations

import asyncio
from dataclasses import fields

import pytest

from app.services import total_comp_core as core
from app.services import total_comp_service as svc

ORG = "11111111-1111-1111-1111-111111111111"
EMP = "22222222-2222-2222-2222-222222222222"


def test_cash_comp_carries_availability_like_its_siblings():
    names = {f.name for f in fields(core.CashComp)}
    for required in ("available", "reason"):
        assert required in names, (
            f"CashComp has no {required!r}; a caller cannot tell a missing "
            "record from a salary of zero")
    # ...and the siblings it is being matched to still have it.
    for sibling in (core.CommissionComp, core.PayrollActualComp):
        assert {"available", "reason"} <= {f.name for f in fields(sibling)}


def test_a_default_cash_comp_is_not_available():
    c = core.CashComp()
    assert c.available is False
    assert c.reason, "an unavailable CashComp must say why"


class _NoRowsDB:
    async def execute(self, *a, **k):
        class R:
            def mappings(self_inner):
                class M:
                    def first(self_m):
                        return None
                return M()
        return R()


class _BrokenDB:
    async def execute(self, *a, **k):
        raise RuntimeError("comp_records does not exist")


@pytest.mark.parametrize("db,expect", [
    (_NoRowsDB(), "no compensation record"),
    (_BrokenDB(), "could not be read"),
])
def test_missing_and_broken_are_distinguishable(db, expect):
    c = asyncio.run(svc._fetch_cash(db, ORG, EMP, 2026))
    assert c.available is False
    assert expect in (c.reason or ""), (
        f"expected a reason mentioning {expect!r}, got {c.reason!r}")


def test_no_employee_selected_is_its_own_reason():
    c = asyncio.run(svc._fetch_cash(_NoRowsDB(), ORG, None, 2026))
    assert c.available is False
    assert "no employee" in (c.reason or "").lower()


def test_the_payload_exposes_the_cash_block():
    payload = core.assemble_total_comp(
        employee_id=EMP,
        plan_year=2026,
        cash=core.CashComp(),
        commission=core.CommissionComp(),
        payroll_actual=core.PayrollActualComp(),
        equity=core.EquityComp(),
        current_fmv=0.0,
    )
    assert "cash" in payload, "the payload has no cash block for a screen to read"
    assert payload["cash"]["available"] is False
    assert payload["cash"]["reason"]
