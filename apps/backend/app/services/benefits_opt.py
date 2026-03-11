from __future__ import annotations

from typing import Any, Dict
from uuid import UUID
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _score(plan_type: str, pref: Dict[str, Any]) -> float:
    lvl = (pref.get(plan_type) or "medium").lower()
    return {"low": 1.0, "medium": 2.0, "high": 3.0}.get(lvl, 2.0)


async def run_optimizer(
    db: AsyncSession,
    org_id: UUID,
    fiscal_year: int,
    budget: float,
) -> Dict[str, Any]:
    plans = (
        await db.execute(
            text(
                """
                select id, category, employer_cost, name
                from public.benefit_plans
                where org_id = :org_id
                """
            ),
            {"org_id": org_id},
        )
    ).fetchall()

    emps = (
        await db.execute(
            text(
                """
                select id
                from public.employees
                where org_id = :org_id
                  and status = 'active'
                """
            ),
            {"org_id": org_id},
        )
    ).fetchall()

    prefs: Dict[str, Any] = {}
    try:
        prefs_rows = (
            await db.execute(
                text(
                    """
                    select employee_id, preferences
                    from public.benefit_preferences
                    where org_id = :org_id
                    """
                ),
                {"org_id": org_id},
            )
        ).fetchall()
        prefs = {str(eid): (p or {}) for eid, p in prefs_rows}
    except Exception:
        await db.rollback()
        prefs = {}

    remaining = float(budget)
    assignments = []

    for (emp_id,) in emps:
        pref = prefs.get(str(emp_id), {})
        ranked = []

        for pid, plan_type, cost, name in plans:
            annual = float(cost or 0.0) * 12.0
            if annual <= 0:
                continue

            value = _score(str(plan_type or "general"), pref) / (annual + 1.0)
            ranked.append((value, pid, plan_type, annual, name))

        ranked.sort(reverse=True)

        for _value, pid, plan_type, annual, name in ranked[:3]:
            if annual <= remaining:
                assignments.append(
                    {
                        "employee_id": str(emp_id),
                        "plan_id": str(pid),
                        "plan_type": plan_type,
                        "annual_employer_cost": round(annual, 2),
                        "name": name,
                    }
                )
                remaining -= annual
                break

    result = {
        "fiscal_year": fiscal_year,
        "budget": budget,
        "remaining": round(remaining, 2),
        "assignments": assignments,
    }

    await db.execute(
        text(
            """
            insert into public.benefit_optimization_runs(
                org_id,
                fiscal_year,
                budget,
                result,
                created_at
            )
            values (
                :org_id,
                :fy,
                :budget,
                cast(:result as jsonb),
                now()
            )
            """
        ),
        {
            "org_id": org_id,
            "fy": fiscal_year,
            "budget": budget,
            "result": json.dumps(result),
        },
    )

    await db.commit()
    return result


async def optimize_benefits(
    db: AsyncSession,
    org_id: UUID,
    fiscal_year: int,
    budget: float,
) -> Dict[str, Any]:
    return await run_optimizer(db, org_id, fiscal_year, budget)
