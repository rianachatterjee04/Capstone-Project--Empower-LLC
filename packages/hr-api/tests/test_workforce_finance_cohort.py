"""
Workforce finance says which of its numbers are the reader's.

WHY THIS IS A TEST
/app/finance showed "Annual loaded payroll $1.98M · 10 employees · Comp budget
$2.40M · Budget variance -17.3% · Hiring delta $454K · 2 open reqs" for an
organisation with one employee.

`overview()` starts `rows = EMPLOYEE_COMP` — a module constant of ten invented
people with invented salaries. Payroll, headcount, budget posture, the
department slices and the twelve-month forecast all describe them.

The open requisitions and the hiring delta are real: _open_reqs queries this
org's job postings. That mixture is worse than either half on its own, because
the two true numbers lend the ten invented ones their credibility — and it is
the same $2.4M envelope and -17.3% variance that the narrative-analytics page
was asserting with no query at all.
"""
from __future__ import annotations

import asyncio

from app.services import workforce_finance_service as F


class _DB:
    """One active employee; a job-postings query returns no rows."""

    async def execute(self, stmt, params=None):
        sql = str(stmt)

        class Res:
            def first(self_inner):
                return (1,) if "employees" in sql else (0,)

            def mappings(self_inner):
                class M:
                    def all(self_m):
                        return []
                return M()
        return Res()


def _overview():
    return asyncio.run(F.overview(_DB(), "11111111-1111-1111-1111-111111111111"))


def test_the_cohort_is_declared_as_a_sample():
    out = _overview()
    c = out["cohort"]
    assert c["is_sample"] is True
    assert c["sample_headcount"] == len(F.EMPLOYEE_COMP)
    assert c["your_active_employees"] == 1
    assert "not from your" in c["note"]


def test_the_split_between_real_and_sample_inputs_is_stated():
    c = _overview()["cohort"]
    assert "open requisitions" in c["real_inputs"], (
        "the open requisitions are read from the org's own job postings and "
        "should be credited as real")
    for sampled in ("payroll", "comp budget", "budget variance"):
        assert sampled in c["sample_inputs"], (
            f"{sampled} is computed from EMPLOYEE_COMP and is not marked as such")


def test_headcount_still_reports_the_cohort_it_priced():
    """CONTROL. The disclosure must not silently change the arithmetic.

    Relabelling is the fix; quietly swapping headcount to the real employee
    count would make payroll-per-head nonsense and hide the discrepancy the
    banner exists to explain.
    """
    out = _overview()
    assert out["headcount"] == len(F.EMPLOYEE_COMP)
    assert out["annual_payroll_base"] == sum(r["salary"] for r in F.EMPLOYEE_COMP)
