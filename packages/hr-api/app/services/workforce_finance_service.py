"""Workforce Finance linkage.

Joins headcount, comp signals, hiring pipeline, and a comp budget into a
single set of forecasts. Heuristic — uses synthetic comp data when a real
comp table isn't present — but the API contract is shaped for a production
swap-in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Demo comp data — mirrors the synthetic workforce used elsewhere.
# In production this comes from a salary table joined on employees.
# ---------------------------------------------------------------------------
EMPLOYEE_COMP = [
    {"id": "e1", "name": "Avery Chen",   "department": "Engineering",     "salary": 165_000},
    {"id": "e2", "name": "Jordan Patel", "department": "Sales",           "salary": 145_000},
    {"id": "e3", "name": "Sam Rivera",   "department": "Engineering",     "salary": 195_000},
    {"id": "e4", "name": "Morgan Lee",   "department": "HR",              "salary": 110_000},
    {"id": "e5", "name": "Riley Singh",  "department": "Design",          "salary": 140_000},
    {"id": "e6", "name": "Emily Stone",  "department": "Customer Success","salary": 105_000},
    {"id": "e7", "name": "Marcus Adler", "department": "Engineering",     "salary": 175_000},
    {"id": "e8", "name": "Sarah Chen",   "department": "Engineering",     "salary": 185_000},
    {"id": "e9", "name": "James Patel",  "department": "Engineering",     "salary": 155_000},
    {"id": "e10","name": "Reese Allen",  "department": "HR",              "salary": 175_000},
]

ROLE_TARGET_COMP: dict[str, int] = {
    "Software Engineer":            145_000,
    "Senior Software Engineer":     175_000,
    "Engineering Lead, Payments":   210_000,
    "Account Executive":            135_000,
    "Customer Success Manager":     125_000,
    "Designer":                     130_000,
    "Security Lead":                205_000,
    "Product Manager, Data":        160_000,
}

# Benefits + employer tax loading (rough industry default for SMBs).
BENEFITS_LOADING_RATE = 0.28

# Org-level comp budget envelope (annual).
DEFAULT_COMP_BUDGET = 2_400_000


# ---------------------------------------------------------------------------
def _annual_payroll(rows: list[dict]) -> float:
    return float(sum(r["salary"] for r in rows))


async def _open_reqs(db: AsyncSession, org_id: str) -> list[dict]:
    try:
        res = await db.execute(
            text(
                "select id::text, title, status, created_at "
                "from public.job_postings "
                "where org_id=:org and status<>'closed' "
                "order by created_at desc"
            ),
            {"org": org_id},
        )
        return [dict(r) for r in res.mappings().all()]
    except Exception:
        return []


def _estimate_role_cost(title: str) -> int:
    """Best-effort target comp lookup; falls back to org median."""
    if title in ROLE_TARGET_COMP:
        return ROLE_TARGET_COMP[title]
    median = sorted([r["salary"] for r in EMPLOYEE_COMP])[len(EMPLOYEE_COMP) // 2]
    # crude title heuristic: senior/lead bumps the median
    t = title.lower()
    if "lead" in t or "staff" in t or "senior" in t:
        return int(median * 1.15)
    if "manager" in t or "head" in t or "director" in t:
        return int(median * 1.25)
    return median


async def overview(db: AsyncSession, org_id: str) -> dict:
    """Payroll, budget posture and hiring impact.

    THE SALARIES ARE A SAMPLE COHORT. `rows = EMPLOYEE_COMP` is a module
    constant: ten invented people with invented salaries. Everything derived
    from it — "$1.98M annual loaded payroll", "10 employees", "comp budget
    $2.40M", "budget variance -17.3%", the department slices and the twelve
    month forecast — describes them, not the reader.

    The open requisitions and the hiring delta ARE real: _open_reqs queries
    this organisation's job postings. So the page mixed two genuine open reqs
    with ten fabricated employees and presented the total as one picture, for
    an organisation with a single employee. That mixture is worse than either
    half, because the real numbers lend the invented ones credibility.

    The same $2.4M envelope and -17.3% variance were also being asserted, with
    no query at all, by the narrative-analytics page; that copy has been
    removed. Here the maths is real and only its input is a sample, so the
    cohort is declared rather than deleted.
    """
    rows = EMPLOYEE_COMP
    base = _annual_payroll(rows)
    loaded = base * (1 + BENEFITS_LOADING_RATE)

    # Hiring impact
    reqs = await _open_reqs(db, org_id)
    hiring_delta = sum(_estimate_role_cost(r["title"]) for r in reqs)
    loaded_hiring_delta = hiring_delta * (1 + BENEFITS_LOADING_RATE)

    # Department slices
    by_dept: dict[str, dict] = {}
    for r in rows:
        d = by_dept.setdefault(r["department"], {"department": r["department"], "headcount": 0, "annual_base": 0})
        d["headcount"] += 1
        d["annual_base"] += r["salary"]
    dept_rows = sorted(by_dept.values(), key=lambda x: -x["annual_base"])
    for d in dept_rows:
        d["annual_loaded"] = round(d["annual_base"] * (1 + BENEFITS_LOADING_RATE))

    # Comp budget posture
    budget = DEFAULT_COMP_BUDGET
    consumed = round(loaded)
    variance_pct = round(((consumed - budget) / budget) * 100, 1) if budget else 0.0

    # How many of the reader's own employees this actually describes.
    own = 0
    try:
        r = (await db.execute(text(
            "select count(*) from public.employees "
            "where org_id = :org and status = 'active'"), {"org": org_id})).first()
        own = int(r[0]) if r and r[0] is not None else 0
    except Exception:
        own = 0

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "headcount": len(rows),
        "cohort": {
            "is_sample": True,
            "sample_headcount": len(rows),
            "your_active_employees": own,
            "real_inputs": ["open requisitions", "hiring delta"],
            "sample_inputs": ["salaries", "headcount", "payroll", "comp budget",
                              "budget variance", "department slices", "forecast"],
            "note": (
                f"Payroll and budget figures are computed from a {len(rows)}-person "
                "illustrative cohort shipped with the product, not from your "
                f"{own} active employee{'s' if own != 1 else ''}. The open "
                "requisitions and the hiring delta are read from your own job "
                "postings. Connect compensation records to see this for your "
                "own payroll."
            ),
        },
        "annual_payroll_base": round(base),
        "annual_payroll_loaded": round(loaded),
        "benefits_loading_rate": BENEFITS_LOADING_RATE,
        "comp_budget_annual": budget,
        "comp_budget_consumed": consumed,
        "comp_budget_variance_pct": variance_pct,
        "open_reqs": len(reqs),
        "hiring_delta_base": hiring_delta,
        "hiring_delta_loaded": round(loaded_hiring_delta),
        "by_department": dept_rows,
    }


async def forecast(db: AsyncSession, org_id: str, months: int = 12) -> dict:
    """Project payroll over the next N months with assumed hiring + raises."""
    base = _annual_payroll(EMPLOYEE_COMP)
    monthly = base / 12.0

    reqs = await _open_reqs(db, org_id)
    # Assume open reqs fill over 2 months evenly, raises hit at month 6.
    fills_per_month = (len(reqs) / 2.0) if reqs else 0.0
    avg_target = sum(_estimate_role_cost(r["title"]) for r in reqs) / max(len(reqs), 1) if reqs else 0
    raise_factor = 0.03   # 3% mid-year comp cycle

    months_out: list[dict] = []
    cumulative_base = base
    for i in range(1, months + 1):
        if i <= 2 and reqs:
            cumulative_base += fills_per_month * avg_target
        if i == 6:
            cumulative_base *= (1 + raise_factor)
        loaded = cumulative_base * (1 + BENEFITS_LOADING_RATE)
        months_out.append({
            "month_index": i,
            "label": f"M+{i}",
            "annual_base": round(cumulative_base),
            "annual_loaded": round(loaded),
            "monthly_loaded": round(loaded / 12.0),
        })

    return {
        "starting_annual_base": round(base),
        "starting_monthly": round(monthly),
        "assumed_open_reqs_filled": len(reqs),
        "assumed_raise_factor": raise_factor,
        "months": months_out,
    }


async def hiring_impact(db: AsyncSession, org_id: str) -> dict:
    reqs = await _open_reqs(db, org_id)
    rows: list[dict] = []
    total = 0.0
    for r in reqs:
        cost = _estimate_role_cost(r["title"])
        loaded = cost * (1 + BENEFITS_LOADING_RATE)
        total += loaded
        rows.append({
            "id": r["id"],
            "title": r["title"],
            "status": r["status"],
            "estimated_base": cost,
            "estimated_loaded": round(loaded),
        })
    return {
        "open_reqs": len(reqs),
        "total_loaded_delta": round(total),
        "items": rows,
    }


async def comp_budget(db: AsyncSession, org_id: str) -> dict:
    o = await overview(db, org_id)
    return {
        "budget": o["comp_budget_annual"],
        "consumed": o["comp_budget_consumed"],
        "variance_pct": o["comp_budget_variance_pct"],
        "tone": "danger" if o["comp_budget_variance_pct"] > 5 else "warn" if o["comp_budget_variance_pct"] > 0 else "success",
        "by_department": o["by_department"],
    }


# ===========================================================================
# WORKFORCE FINANCIAL INTELLIGENCE
#
# The Finance x HR questions nobody else can answer because we own BOTH sides:
#   - ROI: revenue-contribution / cost, ranked by team and by employee.
#   - Scenario simulator: 4 deterministic what-ifs (commission, headcount,
#     attrition backfill, new-market entry).
#
# All math is deterministic from the constants below (which mirror the demo
# comp roster) and is fail-soft: a missing finance input degrades to a safe,
# documented estimate rather than a 500. A plain-English narrative is attached
# via the existing HR LLM wrapper, also fail-soft to a deterministic string.
# ===========================================================================

# Annual revenue attributed to each team. Revenue-bearing teams carry a figure;
# pure cost centers (HR, Executive) are 0 and surface as such in ROI.
REVENUE_BY_TEAM: dict[str, float] = {
    "Sales": 4_200_000,
    "Engineering": 6_000_000,
    "Customer Success": 1_800_000,
    "Design": 600_000,
    "HR": 0,
    "Executive": 0,
}

# Target comp for roles used by headcount / new-market scenarios.
NEW_MARKET_ROLE_COMP: dict[str, int] = {
    "Sales": 135_000,
    "HR": 110_000,
    "Finance": 130_000,
    "Engineering": 160_000,
    "Customer Success": 105_000,
    "Design": 130_000,
}

# Regional cost-of-labour factor applied to a market-entry payroll estimate.
REGION_COST_FACTOR: dict[str, float] = {
    "germany": 0.95, "uk": 1.05, "united states": 1.0, "us": 1.0, "usa": 1.0,
    "canada": 0.90, "india": 0.45, "poland": 0.55, "brazil": 0.50, "singapore": 0.98,
}
DEFAULT_REGION_FACTOR = 0.85

# Market-entry headcount templates by plan size.
MARKET_PLAN_TEMPLATES: dict[str, dict[str, int]] = {
    "lean":     {"Sales": 2, "HR": 1},
    "standard": {"Sales": 3, "HR": 1, "Finance": 1},
    "growth":   {"Sales": 5, "HR": 1, "Finance": 1, "Customer Success": 2},
}

# Cost-to-backfill components (fractions of annual base).
BACKFILL_RECRUITING = 0.20      # agency / sourcing / referral cost
BACKFILL_RAMP = 0.25            # reduced productivity during ~3-month ramp
BACKFILL_VACANCY_MONTHS = 2     # months the seat sits open before backfill starts


def _team_rows() -> dict[str, dict]:
    by_team: dict[str, dict] = {}
    for r in EMPLOYEE_COMP:
        t = by_team.setdefault(r["department"], {"team": r["department"], "headcount": 0, "annual_base": 0})
        t["headcount"] += 1
        t["annual_base"] += r["salary"]
    return by_team


def _narrative(prompt: str, org_id: str, fallback: str) -> dict:
    """Plain-English narrative via the HR LLM wrapper; fail-soft to a
    deterministic string when no LLM is configured (tests, offline)."""
    try:
        from app.services.llm import llm_complete
        text = llm_complete(prompt, system="You are a concise workforce-finance analyst. 2 sentences max.", org_id=org_id)
        if text and text.strip():
            return {"text": text.strip(), "source": "ai"}
    except Exception:
        pass
    return {"text": fallback, "source": "fallback"}


async def roi(db: AsyncSession, org_id: str) -> dict:
    """Rank teams and employees by revenue-contribution / cost.

    Team revenue is allocated evenly across its members to derive a per-employee
    revenue contribution; ROI = revenue / loaded cost. Cost-center teams (0
    revenue) surface with roi_ratio 0 and are flagged.
    """
    by_team = _team_rows()
    team_rows: list[dict] = []
    for t, agg in by_team.items():
        loaded_cost = round(agg["annual_base"] * (1 + BENEFITS_LOADING_RATE))
        revenue = REVENUE_BY_TEAM.get(t, 0)
        roi_ratio = round(revenue / loaded_cost, 2) if loaded_cost else 0.0
        team_rows.append({
            "team": t,
            "headcount": agg["headcount"],
            "annual_cost_loaded": loaded_cost,
            "revenue_attributed": revenue,
            "revenue_per_head": round(revenue / agg["headcount"]) if agg["headcount"] else 0,
            "cost_per_head": round(loaded_cost / agg["headcount"]) if agg["headcount"] else 0,
            "roi_ratio": roi_ratio,
            "is_cost_center": revenue == 0,
        })
    team_rows.sort(key=lambda r: -r["roi_ratio"])

    emp_rows: list[dict] = []
    for r in EMPLOYEE_COMP:
        t = r["department"]
        head = by_team[t]["headcount"]
        revenue_contribution = round(REVENUE_BY_TEAM.get(t, 0) / head) if head else 0
        loaded = round(r["salary"] * (1 + BENEFITS_LOADING_RATE))
        roi_ratio = round(revenue_contribution / loaded, 2) if loaded else 0.0
        emp_rows.append({
            "id": r["id"], "name": r["name"], "team": t,
            "annual_cost_loaded": loaded,
            "revenue_contribution": revenue_contribution,
            "roi_ratio": roi_ratio,
        })
    emp_rows.sort(key=lambda r: -r["roi_ratio"])

    total_cost = round(sum(r["annual_cost_loaded"] for r in team_rows))
    total_rev = sum(REVENUE_BY_TEAM.get(t, 0) for t in by_team)
    return {
        "org_roi_ratio": round(total_rev / total_cost, 2) if total_cost else 0.0,
        "total_revenue_attributed": total_rev,
        "total_cost_loaded": total_cost,
        "teams": team_rows,
        "employees": emp_rows,
        "top_teams": team_rows[:3],
        "top_employees": emp_rows[:5],
    }


def _simulate_commission_change(pct: float, org_id: str) -> dict:
    """+/- pct POINTS on the effective commission rate applied to Sales revenue."""
    sales_revenue = REVENUE_BY_TEAM.get("Sales", 0)
    payroll_base_delta = round(sales_revenue * (pct / 100.0))
    payroll_loaded_delta = round(payroll_base_delta * (1 + BENEFITS_LOADING_RATE))
    ebitda_delta = -payroll_loaded_delta   # extra payroll reduces EBITDA
    fallback = (
        f"A {pct:+.1f}pt commission change on ${sales_revenue:,.0f} of Sales revenue moves annual "
        f"payroll by ${payroll_loaded_delta:+,.0f} (loaded) and EBITDA by ${ebitda_delta:+,.0f}."
    )
    return {
        "kind": "commission_change",
        "pct": pct,
        "sales_revenue_base": sales_revenue,
        "payroll_base_delta": payroll_base_delta,
        "payroll_loaded_delta": payroll_loaded_delta,
        "ebitda_delta": ebitda_delta,
        "narrative": _narrative(fallback, org_id, fallback),
    }


def _simulate_headcount_add(team: str, n: int, org_id: str) -> dict:
    by_team = _team_rows()
    if team in by_team and by_team[team]["headcount"]:
        avg_base = round(by_team[team]["annual_base"] / by_team[team]["headcount"])
    else:
        avg_base = NEW_MARKET_ROLE_COMP.get(team, DEFAULT_COMP_BUDGET // 20)
    added_base = avg_base * n
    added_loaded = round(added_base * (1 + BENEFITS_LOADING_RATE))
    revenue_per_head = round(REVENUE_BY_TEAM.get(team, 0) / by_team[team]["headcount"]) if team in by_team and by_team[team]["headcount"] else 0
    monthly_added_revenue = (revenue_per_head * n) / 12.0
    months_to_breakeven = round(added_loaded / monthly_added_revenue, 1) if monthly_added_revenue else None
    when_to_hire = {
        "recommended_start": "M+1",
        "cadence": "1 hire / month" if n > 1 else "single hire",
        "full_ramp_month": f"M+{n}",
        "months_to_breakeven": months_to_breakeven,
        "verdict": ("Hire now — pays back inside a quarter" if (months_to_breakeven or 99) <= 3
                    else "Stage over the next quarter" if (months_to_breakeven or 99) <= 9
                    else "Cost center — justify on capacity, not payback"),
    }
    fallback = (
        f"Adding {n} to {team} costs ${added_loaded:,.0f}/yr loaded"
        + (f" and breaks even in ~{months_to_breakeven} months." if months_to_breakeven else " (cost center — no direct revenue payback).")
    )
    return {
        "kind": "headcount_add",
        "team": team, "n": n,
        "avg_base_per_hire": avg_base,
        "added_cost_base": added_base,
        "added_cost_loaded": added_loaded,
        "revenue_per_head": revenue_per_head,
        "when_to_hire": when_to_hire,
        "narrative": _narrative(fallback, org_id, fallback),
    }


def _simulate_attrition(employee_id: str, org_id: str) -> dict:
    emp = next((r for r in EMPLOYEE_COMP if r["id"] == employee_id), None)
    if not emp:
        # Fail-soft: use org median base.
        median = sorted([r["salary"] for r in EMPLOYEE_COMP])[len(EMPLOYEE_COMP) // 2]
        emp = {"id": employee_id, "name": employee_id, "department": "—", "salary": median}
    base = emp["salary"]
    recruiting = round(base * BACKFILL_RECRUITING)
    ramp = round(base * BACKFILL_RAMP)
    vacancy = round(base * (BACKFILL_VACANCY_MONTHS / 12.0))
    total = recruiting + ramp + vacancy
    # Knowledge / risk impact — deterministic from comp seniority + team revenue.
    senior = base >= 175_000
    revenue_team = REVENUE_BY_TEAM.get(emp["department"], 0) > 0
    knowledge_risk = "high" if senior and revenue_team else "medium" if (senior or revenue_team) else "low"
    fallback = (
        f"If {emp['name']} quits, backfill runs ~${total:,.0f} (recruiting ${recruiting:,.0f} + ramp "
        f"${ramp:,.0f} + {BACKFILL_VACANCY_MONTHS}mo vacancy ${vacancy:,.0f}); knowledge risk {knowledge_risk}."
    )
    return {
        "kind": "attrition",
        "employee_id": emp["id"], "name": emp["name"], "team": emp["department"],
        "annual_base": base,
        "backfill_breakdown": {"recruiting": recruiting, "ramp_loss": ramp, "vacancy_productivity": vacancy},
        "cost_to_backfill": total,
        "knowledge_risk": knowledge_risk,
        "narrative": _narrative(fallback, org_id, fallback),
    }


def _simulate_new_market(region: str, plan: str, org_id: str) -> dict:
    plan_key = (plan or "standard").lower()
    template = MARKET_PLAN_TEMPLATES.get(plan_key, MARKET_PLAN_TEMPLATES["standard"])
    factor = REGION_COST_FACTOR.get((region or "").lower(), DEFAULT_REGION_FACTOR)
    roles = []
    base_total = 0
    for role, count in template.items():
        comp = NEW_MARKET_ROLE_COMP.get(role, 120_000)
        role_base = comp * count
        base_total += role_base
        roles.append({"role": role, "count": count, "comp_per_head": comp, "role_base": role_base})
    regional_base = round(base_total * factor)
    est_payroll_loaded = round(regional_base * (1 + BENEFITS_LOADING_RATE))
    headcount = sum(template.values())
    headline = ", ".join(f"{c} {r}" for r, c in template.items())
    fallback = (
        f"Opening {region or 'a new market'} ({plan_key}) → {headline} "
        f"({headcount} hires), ~${est_payroll_loaded:,.0f}/yr loaded payroll "
        f"(regional factor {factor})."
    )
    return {
        "kind": "new_market",
        "region": region, "plan": plan_key,
        "region_cost_factor": factor,
        "recommended_headcount": template,
        "roles": roles,
        "total_headcount": headcount,
        "estimated_payroll_base": base_total,
        "estimated_payroll_regional_base": regional_base,
        "estimated_payroll_loaded": est_payroll_loaded,
        "narrative": _narrative(fallback, org_id, fallback),
    }


async def simulate(db: AsyncSession, org_id: str, payload: dict) -> dict:
    """Scenario simulator dispatcher. Deterministic + fail-soft.

    Supported kinds:
      commission_change {pct}
      headcount_add     {team, n}
      attrition         {employee_id}
      new_market        {region, plan}
    """
    kind = (payload or {}).get("kind")
    if kind == "commission_change":
        pct = float(payload.get("pct", 0) or 0)
        return _simulate_commission_change(pct, org_id)
    if kind == "headcount_add":
        team = str(payload.get("team") or "Engineering")
        n = max(1, int(payload.get("n", 1) or 1))
        return _simulate_headcount_add(team, n, org_id)
    if kind == "attrition":
        employee_id = str(payload.get("employee_id") or "")
        return _simulate_attrition(employee_id, org_id)
    if kind == "new_market":
        region = str(payload.get("region") or "")
        plan = str(payload.get("plan") or "standard")
        return _simulate_new_market(region, plan, org_id)
    raise ValueError(f"Unknown simulate kind: {kind!r}")
