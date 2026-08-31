"""Workforce Graph — the org chart for the AI era.

This is the one thing no HRIS (Workday / Rippling / BambooHR) and no hiring
marketplace (Mercor) can build: a SINGLE graph of the *entire* workforce —
humans, AI agents, contractors, and bots — in one reporting hierarchy, where
every node carries a **trust score** and a **risk score**.

Why Fintra can build it: we own Finance (comp / run-cost), HR (people / org /
performance), AND the SentriAI trust layer (agent scopes / approvals). No one
else owns all three, so no one else can put a human and an AI worker on the same
map, each with a trust score, priced against the same P&L.

Design:
  - Deterministic, in-process canonical workforce (mirrors the goals /
    recognition seeded-store pattern) so the graph is testable DB-free and
    stable between renders.
  - Fail-soft: if a real employees table is present we swap the *human* nodes in
    from the DB; if anything fails we fall back to the canonical seed. AI agents
    / contractors / bots always come from the in-process registry (they are not
    HRIS rows).
  - Human risk reuses the existing attrition model (app.services.attrition_service).
    AI-agent / bot trust is computed by a documented deterministic formula from
    each agent's approval track record, incident count, and scope sensitivity.

Node types: human | ai_agent | contractor | bot
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services.attrition_service import AttritionFeatures, predict, predict_batch


# ---------------------------------------------------------------------------
# Cost / finance constants (kept in sync with workforce_finance_service).
# ---------------------------------------------------------------------------
BENEFITS_LOADING_RATE = 0.28   # benefits + employer tax loading on human cash comp

# Scopes we treat as sensitive when scoring AI / bot risk. Broad access to money,
# comp, or PII raises the blast radius of a low-trust agent.
SENSITIVE_SCOPES = {
    "payroll.write", "payroll.run", "comp.write", "funds.move",
    "pii.read", "pii.write", "offer.send", "contract.sign", "term.execute",
}


# ---------------------------------------------------------------------------
# Canonical workforce seed.
# Humans mirror workforce_finance_service.EMPLOYEE_COMP so comp is consistent.
# ---------------------------------------------------------------------------
def _human_seed() -> list[dict]:
    return [
        {"id": "ceo", "name": "Casey Reed",   "role": "CEO",                     "team": "Executive",       "manager_id": None,  "salary": 320_000, "skills": ["strategy", "leadership"],               "perf_rating": 4.6, "tenure_years": 6.0},
        {"id": "e3",  "name": "Sam Rivera",    "role": "Engineering Lead",        "team": "Engineering",     "manager_id": "ceo", "salary": 195_000, "skills": ["python", "kubernetes", "postgres"],    "perf_rating": 4.0, "tenure_years": 3.6},
        {"id": "e10", "name": "Reese Allen",   "role": "VP People",               "team": "HR",              "manager_id": "ceo", "salary": 175_000, "skills": ["people ops", "comp", "org design"],    "perf_rating": 4.3, "tenure_years": 4.1},
        {"id": "vps", "name": "Jamie Cole",    "role": "VP Sales",                "team": "Sales",           "manager_id": "ceo", "salary": 205_000, "skills": ["sales", "pipeline", "quota"],          "perf_rating": 4.2, "tenure_years": 3.2},
        {"id": "e1",  "name": "Avery Chen",    "role": "Senior Software Engineer","team": "Engineering",     "manager_id": "e3",  "salary": 165_000, "skills": ["python", "fastapi", "postgres"],       "perf_rating": 4.5, "tenure_years": 2.4},
        {"id": "e7",  "name": "Marcus Adler",  "role": "Software Engineer",       "team": "Engineering",     "manager_id": "e3",  "salary": 175_000, "skills": ["react", "typescript", "next.js"],      "perf_rating": 3.9, "tenure_years": 2.1},
        {"id": "e8",  "name": "Sarah Chen",    "role": "Staff Software Engineer", "team": "Engineering",     "manager_id": "e3",  "salary": 185_000, "skills": ["python", "go", "kubernetes"],          "perf_rating": 4.7, "tenure_years": 3.9},
        {"id": "e9",  "name": "James Patel",   "role": "Software Engineer",       "team": "Engineering",     "manager_id": "e3",  "salary": 155_000, "skills": ["typescript", "react", "graphql"],      "perf_rating": 3.8, "tenure_years": 1.6},
        {"id": "e2",  "name": "Jordan Patel",  "role": "Account Executive",       "team": "Sales",           "manager_id": "vps", "salary": 145_000, "skills": ["sales", "outbound", "close"],          "perf_rating": 3.2, "tenure_years": 1.8},
        {"id": "e5",  "name": "Riley Singh",   "role": "Senior Designer",         "team": "Design",          "manager_id": "ceo", "salary": 140_000, "skills": ["figma", "ux", "prototype"],            "perf_rating": 4.8, "tenure_years": 2.0},
        {"id": "e6",  "name": "Emily Stone",   "role": "CS Manager",              "team": "Customer Success","manager_id": "e10", "salary": 105_000, "skills": ["customer success", "onboarding"],      "perf_rating": 4.6, "tenure_years": 1.8},
        {"id": "e4",  "name": "Morgan Lee",    "role": "HR Business Partner",     "team": "HR",              "manager_id": "e10", "salary": 110_000, "skills": ["hr", "policy", "employee relations"],  "perf_rating": 3.6, "tenure_years": 0.6},
    ]


# Attrition feature overrides for the humans the model has rich signal on. Any
# human not listed gets a neutral default (=> low band). Deterministic.
_ATTR_FEATURES = {
    "e1": dict(department="Engineering", tenure_years=2.4, months_since_last_raise=22, months_since_last_promotion=30, performance_rating=4.5, engagement_score=0.42, compa_ratio=0.82, overtime_hours_last_30d=38),
    "e2": dict(department="Sales", tenure_years=1.8, months_since_last_raise=14, months_since_last_promotion=20, performance_rating=3.2, engagement_score=0.61, compa_ratio=0.97, pto_balance_days=22),
    "e5": dict(department="Design", tenure_years=2.0, months_since_last_raise=18, months_since_last_promotion=24, performance_rating=4.8, compa_ratio=0.88, role_change_in_last_180d=True, pto_balance_days=19),
    "e6": dict(department="Customer Success", tenure_years=1.8, performance_rating=4.6, compa_ratio=0.94, engagement_score=0.71),
    "e8": dict(department="Engineering", tenure_years=3.9, months_since_last_raise=9, months_since_last_promotion=11, performance_rating=4.7, compa_ratio=1.02, engagement_score=0.8),
}


def _ai_agent_seed() -> list[dict]:
    """AI agents + bots. These map onto the deterministic operators in
    app.services.agent_runtime plus the payroll agent. Each carries the inputs
    the trust formula consumes: approvals granted/rejected/pending, incidents,
    autonomy, scopes, run cost, and a 30-day interaction count."""
    return [
        {"id": "ag_recruiting",  "type": "ai_agent", "name": "Recruiting Agent",     "role": "Sourcing & screening operator", "team": "Recruiting",      "manager_id": "e10", "skills": ["screening", "outreach", "scheduling"],          "annual_run_cost": 18_000, "runs_30d": 240, "approvals_granted": 96, "approvals_rejected": 4,  "approvals_pending": 3, "incidents": 0, "autonomy": "suggest", "scopes": ["ats.read", "ats.write", "offer.send"]},
        {"id": "ag_onboarding",  "type": "ai_agent", "name": "Onboarding Agent",     "role": "Day-1 & provisioning operator", "team": "HR",              "manager_id": "e10", "skills": ["provisioning", "docs", "scheduling"],           "annual_run_cost": 12_000, "runs_30d": 130, "approvals_granted": 60, "approvals_rejected": 2,  "approvals_pending": 1, "incidents": 0, "autonomy": "approve", "scopes": ["pii.read", "hris.write"]},
        {"id": "ag_compliance",  "type": "ai_agent", "name": "HR Compliance Agent",  "role": "Case triage & audit operator",  "team": "Compliance",      "manager_id": "e10", "skills": ["case triage", "audit", "policy"],               "annual_run_cost": 15_000, "runs_30d": 88,  "approvals_granted": 40, "approvals_rejected": 6,  "approvals_pending": 2, "incidents": 1, "autonomy": "suggest", "scopes": ["cases.read", "cases.write", "pii.read"]},
        {"id": "ag_comp",        "type": "ai_agent", "name": "Compensation Agent",   "role": "Comp drift & merit modeler",    "team": "HR",              "manager_id": "e10", "skills": ["comp modeling", "benchmarking"],                "annual_run_cost": 14_000, "runs_30d": 52,  "approvals_granted": 22, "approvals_rejected": 3,  "approvals_pending": 4, "incidents": 0, "autonomy": "suggest", "scopes": ["comp.read", "comp.write"]},
        {"id": "ag_planning",    "type": "ai_agent", "name": "Workforce Planning Agent", "role": "Headcount & burn forecaster","team": "Finance",         "manager_id": "ceo", "skills": ["forecasting", "capacity planning"],             "annual_run_cost": 16_000, "runs_30d": 40,  "approvals_granted": 18, "approvals_rejected": 1,  "approvals_pending": 1, "incidents": 0, "autonomy": "suggest", "scopes": ["finance.read"]},
        {"id": "ag_payroll",     "type": "ai_agent", "name": "Payroll Agent",        "role": "Payroll run & anomaly operator","team": "Finance",         "manager_id": "ceo", "skills": ["payroll", "reconciliation", "anomaly detection"],"annual_run_cost": 22_000, "runs_30d": 24,  "approvals_granted": 20, "approvals_rejected": 0,  "approvals_pending": 2, "incidents": 0, "autonomy": "approve", "scopes": ["payroll.read", "payroll.write", "payroll.run", "funds.move"]},
        {"id": "bot_notifier",   "type": "bot",      "name": "Notifier Bot",         "role": "Slack / email notifier",        "team": "IT",              "manager_id": "e3",  "skills": ["messaging"],                                    "annual_run_cost": 1_200,  "runs_30d": 1400,"approvals_granted": 0,  "approvals_rejected": 0,  "approvals_pending": 0, "incidents": 0, "autonomy": "auto",    "scopes": ["notify.send"]},
        {"id": "bot_atssync",    "type": "bot",      "name": "ATS Sync Bot",         "role": "ATS <-> HRIS sync job",         "team": "IT",              "manager_id": "e3",  "skills": ["etl", "sync"],                                  "annual_run_cost": 2_400,  "runs_30d": 720, "approvals_granted": 0,  "approvals_rejected": 0,  "approvals_pending": 0, "incidents": 2, "autonomy": "auto",    "scopes": ["ats.read", "hris.write", "pii.read"]},
    ]


def _contractor_seed() -> list[dict]:
    return [
        {"id": "c1", "type": "contractor", "name": "Dana Fields", "role": "Contract Product Designer", "team": "Design",      "manager_id": "e5",  "hourly_rate": 95,  "hours_per_week": 30, "skills": ["figma", "ux", "motion"],       "reliability": 0.9, "months_engaged": 8, "scopes": ["design.read", "design.write"]},
        {"id": "c2", "type": "contractor", "name": "Priya Nair",  "role": "Contract Backend Engineer", "team": "Engineering", "manager_id": "e3",  "hourly_rate": 120, "hours_per_week": 40, "skills": ["python", "go", "aws"],         "reliability": 0.82,"months_engaged": 4, "scopes": ["repo.read", "repo.write", "pii.read"]},
    ]


# ---------------------------------------------------------------------------
# Trust / risk scoring
# ---------------------------------------------------------------------------
def _clamp(v: float, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(v))))


def _human_scores(h: dict) -> tuple[int, int, dict]:
    """Returns (trust_score, risk_score, attrition_detail).

    risk = attrition flight-risk (reuse the existing model).
    trust = tenure/performance-based reliability, discounted by flight risk:
        trust = 70 + (perf - 3.0)*10 - 0.25*risk
    """
    feats = _ATTR_FEATURES.get(h["id"])
    if feats is not None:
        pred = predict(AttritionFeatures(employee_id=h["id"], name=h["name"], **feats))
        risk = pred.risk_score
        detail = {"band": pred.band, "drivers": pred.drivers, "suggested_actions": pred.suggested_actions}
    else:
        # Neutral default => low band. Deterministic.
        pred = predict(AttritionFeatures(
            employee_id=h["id"], name=h["name"], department=h["team"],
            tenure_years=(h.get("tenure_years") or 2.0),
            performance_rating=(h.get("perf_rating") or 3.5),
        ))
        risk = pred.risk_score
        detail = {"band": pred.band, "drivers": pred.drivers, "suggested_actions": pred.suggested_actions}
    trust = _clamp(70 + ((h.get("perf_rating") or 3.5) - 3.0) * 10 - 0.25 * risk, 30, 99)
    return trust, risk, detail


def agent_trust_score(a: dict) -> int:
    """Deterministic AI-agent / bot trust score (0-100).

        approval_rate = granted / (granted + rejected)     [1.0 if no decisions yet]
        trust = 50 + 45*approval_rate - 10*incidents - 3*approvals_pending

    A perfect track record with no incidents / pending trends toward ~95; each
    incident costs 10, each pending approval costs 3. Bots that never need
    approval (auto) rest at the 50 + 45 = 95 baseline unless they log incidents.
    """
    granted = a.get("approvals_granted", 0)
    rejected = a.get("approvals_rejected", 0)
    denom = granted + rejected
    approval_rate = (granted / denom) if denom else 1.0
    trust = 50 + 45 * approval_rate - 10 * a.get("incidents", 0) - 3 * a.get("approvals_pending", 0)
    return _clamp(trust)


def agent_risk_score(a: dict, trust: int) -> int:
    """Deterministic AI-agent / bot risk score (0-100).

        risk = (100 - trust) + 4 * (#sensitive scopes) + autonomy_premium

    Broad access to money / comp / PII and higher autonomy widen the blast
    radius, so the same trust score is riskier on a payroll agent than a notifier.
    """
    sensitive = sum(1 for s in a.get("scopes", []) if s in SENSITIVE_SCOPES)
    autonomy_premium = {"suggest": 0, "approve": 6, "auto": 12}.get(a.get("autonomy", "suggest"), 0)
    return _clamp((100 - trust) + 4 * sensitive + autonomy_premium)


def _contractor_scores(c: dict) -> tuple[int, int]:
    """Contractors: trust from reliability + tenure, risk its inverse + scope.

        trust = 40 + 45*reliability + min(months_engaged, 12)*0.8
        risk  = (100 - trust) + 4*(#sensitive scopes)
    """
    trust = _clamp(40 + 45 * c.get("reliability", 0.8) + min(c.get("months_engaged", 0), 12) * 0.8, 30, 95)
    sensitive = sum(1 for s in c.get("scopes", []) if s in SENSITIVE_SCOPES)
    risk = _clamp((100 - trust) + 4 * sensitive)
    return trust, risk


# ---------------------------------------------------------------------------
# Cost normalisation
# ---------------------------------------------------------------------------
def _human_cost(h: dict) -> Optional[float]:
    """Loaded annual cost, or None when no salary is on record."""
    salary = h.get("salary")
    return round(salary * (1 + BENEFITS_LOADING_RATE)) if salary is not None else None


def _contractor_annual_cost(c: dict) -> float:
    # Contractors carry no benefits load; annualised from rate * hours.
    return round(c["hourly_rate"] * c["hours_per_week"] * 52)


# ---------------------------------------------------------------------------
# Node model
# ---------------------------------------------------------------------------
@dataclass
class WorkforceNode:
    id: str
    type: str                    # human | ai_agent | contractor | bot
    name: str
    role: str
    team: str
    manager_id: Optional[str]
    skills: list[str]
    performance: dict
    compensation: dict
    cost_annual: Optional[float]
    permissions: list[str]
    trust_score: Optional[int]
    risk_score: int
    ai_interactions: dict
    # WHERE THIS WORKER CAME FROM.
    #
    # This graph mixes real employee records with seeded operator profiles, and
    # nothing in the payload told them apart. An organisation with one employee
    # rendered "Total workforce 11" and gave every node a trust score, under a
    # header reading "No HRIS or hiring marketplace can show you this."
    #
    #   employee_record  — a row in public.employees
    #   sample_profile   — an illustrative operator; its run counts, approval
    #                      history and incident counts are seeded, so any score
    #                      computed from them is illustrative too
    source: str = "employee_record"
    # Why trust_score is None, when it is.
    trust_basis: Optional[str] = None
    depth: int = 0
    x: int = 0
    y: int = 0
    span: int = 0

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# Layout (deterministic — mirrors org_graph_service)
# ---------------------------------------------------------------------------
def _layout(nodes: list[WorkforceNode]) -> dict:
    by_depth: dict[int, list[WorkforceNode]] = {}
    for n in nodes:
        by_depth.setdefault(n.depth, []).append(n)
    width = 1200
    layer_height = 120
    for depth, layer in by_depth.items():
        layer.sort(key=lambda x: (x.type, x.name))
        gap = width // (len(layer) + 1)
        for idx, n in enumerate(layer, start=1):
            n.x = gap * idx
            n.y = 80 + depth * layer_height
    return {"width": width, "height": 80 + (max((n.depth for n in nodes), default=0) + 1) * layer_height + 40}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def _build_nodes(humans: list[dict]) -> list[WorkforceNode]:
    nodes: list[WorkforceNode] = []

    # Humans
    for h in humans:
        trust, risk, attr = _human_scores(h)
        # A TRUST SCORE ON A NAMED PERSON IS A CLAIM ABOUT THEM.
        # _human_scores falls back to a neutral performance rating of 3.5 when
        # none is recorded, which produced a confident 74 for an employee we
        # hold no performance data on at all. Withheld instead.
        scored = h.get("perf_rating") is not None
        basis = None if scored else (
            "no performance rating on record for this employee, so no trust "
            "score is computed")
        nodes.append(WorkforceNode(
            source="employee_record",
            trust_basis=basis,
            id=h["id"], type="human", name=h["name"], role=h["role"], team=h["team"],
            manager_id=h.get("manager_id"), skills=h.get("skills", []),
            performance={"rating": h.get("perf_rating"), "summary": _perf_summary(h.get("perf_rating")),
                         "attrition_band": attr["band"], "drivers": attr["drivers"]},
            compensation=({"kind": "salary", "annual_base": h["salary"],
                           "annual_loaded": _human_cost(h)}
                          if h.get("salary") is not None else
                          {"kind": "salary", "available": False,
                           "reason": "no salary on record for this employee"}),
            cost_annual=_human_cost(h),
            permissions=["self.read", "team.read"],
            trust_score=(trust if scored else None), risk_score=risk,
            ai_interactions={"kind": "human", "manages_agents": 0, "approvals_pending": 0},
        ))

    # AI agents + bots
    for a in _ai_agent_seed():
        trust = agent_trust_score(a)
        risk = agent_risk_score(a, trust)
        denom = a.get("approvals_granted", 0) + a.get("approvals_rejected", 0)
        approval_rate = round((a.get("approvals_granted", 0) / denom) if denom else 1.0, 3)
        nodes.append(WorkforceNode(
            source="sample_profile",
            trust_basis="computed from seeded run and approval history",
            id=a["id"], type=a["type"], name=a["name"], role=a["role"], team=a["team"],
            manager_id=a.get("manager_id"), skills=a.get("skills", []),
            performance={"rating": None, "summary": f"{a.get('runs_30d', 0)} runs / 30d",
                         "approval_rate": approval_rate, "incidents": a.get("incidents", 0)},
            compensation={"kind": "run_cost", "annual_run_cost": a["annual_run_cost"],
                          "monthly_run_cost": round(a["annual_run_cost"] / 12)},
            cost_annual=float(a["annual_run_cost"]),
            permissions=a.get("scopes", []),
            trust_score=trust, risk_score=risk,
            ai_interactions={"kind": a["type"], "autonomy": a.get("autonomy"), "runs_30d": a.get("runs_30d", 0),
                             "approvals_granted": a.get("approvals_granted", 0),
                             "approvals_rejected": a.get("approvals_rejected", 0),
                             "approvals_pending": a.get("approvals_pending", 0),
                             "approval_rate": approval_rate, "incidents": a.get("incidents", 0)},
        ))

    # Contractors
    for c in _contractor_seed():
        trust, risk = _contractor_scores(c)
        cost = _contractor_annual_cost(c)
        nodes.append(WorkforceNode(
            source="sample_profile",
            trust_basis="computed from seeded engagement history",
            id=c["id"], type="contractor", name=c["name"], role=c["role"], team=c["team"],
            manager_id=c.get("manager_id"), skills=c.get("skills", []),
            performance={"rating": None, "summary": f"{c.get('hours_per_week', 0)}h/wk · {c.get('months_engaged', 0)}mo engaged",
                         "reliability": c.get("reliability")},
            compensation={"kind": "contract", "hourly_rate": c["hourly_rate"], "hours_per_week": c["hours_per_week"],
                          "annual_cost": cost},
            cost_annual=cost,
            permissions=c.get("scopes", []),
            trust_score=trust, risk_score=risk,
            ai_interactions={"kind": "contractor", "approvals_pending": 0},
        ))

    _assign_depth_and_span(nodes)
    _layout(nodes)
    return nodes


def _perf_summary(rating: Optional[float]) -> str:
    if rating is None:
        return "—"
    if rating >= 4.5:
        return "Exceptional"
    if rating >= 4.0:
        return "Strong"
    if rating >= 3.5:
        return "Solid"
    return "Needs support"


def _assign_depth_and_span(nodes: list[WorkforceNode]) -> None:
    by_id = {n.id: n for n in nodes}
    span: dict[str, int] = {}
    for n in nodes:
        if n.manager_id:
            span[n.manager_id] = span.get(n.manager_id, 0) + 1
    for n in nodes:
        n.span = span.get(n.id, 0)

    def depth(nid: str, seen: set[str]) -> int:
        n = by_id.get(nid)
        if not n or not n.manager_id or n.manager_id not in by_id or nid in seen:
            return 0
        seen.add(nid)
        return 1 + depth(n.manager_id, seen)

    for n in nodes:
        n.depth = depth(n.id, set())


def build_workforce(humans: Optional[list[dict]] = None) -> dict:
    """Pure, deterministic builder. Tests call this directly (DB-free)."""
    humans = humans if humans is not None else _human_seed()
    nodes = _build_nodes(humans)
    by_id = {n.id: n for n in nodes}
    edges = [{"source": n.manager_id, "target": n.id, "kind": "reports_to"}
             for n in nodes if n.manager_id and n.manager_id in by_id]
    viewbox = {"width": 1200, "height": 80 + (max((n.depth for n in nodes), default=0) + 1) * 120 + 40}
    return {"nodes": nodes, "edges": edges, "viewbox": viewbox}


def _filter_nodes(nodes: list[WorkforceNode], node_type: Optional[str], team: Optional[str]) -> list[WorkforceNode]:
    out = nodes
    if node_type:
        out = [n for n in out if n.type == node_type]
    if team:
        out = [n for n in out if (n.team or "").lower() == team.lower()]
    return out


# ---------------------------------------------------------------------------
# Public API surface (async wrappers — fail-soft DB swap-in for humans)
# ---------------------------------------------------------------------------
async def _humans_for_org(db, org_id: str) -> list[dict]:
    """Try real employees; fall back to the canonical seed on any failure.

    The real-data path is intentionally conservative: only if we get a
    non-empty, well-formed roster do we use it; otherwise the deterministic seed
    keeps the graph populated (and keeps AI agents anchored to real managers)."""
    try:
        from uuid import UUID
        from sqlalchemy import select
        from app.db.models import Employee
        res = await db.execute(select(Employee).where(Employee.org_id == UUID(org_id)))
        rows = res.scalars().all()
        if not rows:
            return _human_seed()
        seed_by_id = {h["id"]: h for h in _human_seed()}
        humans: list[dict] = []
        for e in rows:
            if e.status in ("terminated", "offboarded"):
                continue
            eid = str(e.id)
            fallback = seed_by_id.get(eid, {})
            humans.append({
                "id": eid,
                "name": e.preferred_name or e.legal_name or fallback.get("name", "—"),
                "role": e.job_title or fallback.get("role", "Employee"),
                "team": e.department or fallback.get("team", "—"),
                "manager_id": str(e.manager_employee_id) if e.manager_employee_id else None,
                # A REAL EMPLOYEE IS NOT A SEED ROW WITH A DIFFERENT NAME.
                # These defaulted to a $120,000 salary, a 3.5 performance
                # rating and two years of tenure for anyone not in the demo
                # seed. A CDL driver we hold no comp record for was drawn on
                # the map with an invented salary, an invented rating and a
                # trust score computed from both, and his invented cost was
                # added into total workforce cost.
                "salary": fallback.get("salary"),
                "skills": fallback.get("skills", []),
                "perf_rating": fallback.get("perf_rating"),
                "tenure_years": fallback.get("tenure_years"),
            })
        return humans or _human_seed()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return _human_seed()


def _provenance(nodes: list) -> dict:
    """How many of these workers are real, and how many are illustrative.

    The graph mixes employees read from public.employees with seeded operator
    profiles, and the payload said nothing about which was which. An
    organisation with a single employee showed "Total workforce 11", every node
    carrying a trust score, under a header reading "No HRIS or hiring
    marketplace can show you this." The claim is a good one; it has to be about
    the customer's own workforce to mean anything.
    """
    real = [n for n in nodes if n.source == "employee_record"]
    sample = [n for n in nodes if n.source != "employee_record"]
    return {
        "employee_records": len(real),
        "sample_profiles": len(sample),
        "note": (
            f"{len(real)} worker{'s' if len(real) != 1 else ''} on this map "
            f"{'are' if len(real) != 1 else 'is'} read from your employee "
            f"records. The other {len(sample)} are illustrative operator "
            "profiles shipped with the product — their run counts, approval "
            "history and engagement hours are sample data, so any score "
            "computed from them is illustrative too."
        ) if sample else "Every worker on this map is read from your employee records.",
    }


async def build_graph(db, org_id: str, *, node_type: Optional[str] = None, team: Optional[str] = None) -> dict:
    humans = await _humans_for_org(db, org_id)
    wf = build_workforce(humans)
    nodes = _filter_nodes(wf["nodes"], node_type, team)
    node_ids = {n.id for n in nodes}
    edges = [e for e in wf["edges"] if e["source"] in node_ids and e["target"] in node_ids]
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "filters": {"type": node_type, "team": team},
        "nodes": [n.to_dict() for n in nodes],
        "edges": edges,
        "viewbox": wf["viewbox"],
        "summary": _summary_from(wf["nodes"]),
        "provenance": _provenance(wf["nodes"]),
    }


async def node_detail(db, org_id: str, node_id: str) -> Optional[dict]:
    humans = await _humans_for_org(db, org_id)
    wf = build_workforce(humans)
    by_id = {n.id: n for n in wf["nodes"]}
    n = by_id.get(node_id)
    if not n:
        return None
    reports = [c.to_dict() for c in wf["nodes"] if c.manager_id == node_id]
    manager = by_id.get(n.manager_id).to_dict() if n.manager_id and n.manager_id in by_id else None
    return {
        "node": n.to_dict(),
        "manager": manager,
        "direct_reports": reports,
        "report_count": len(reports),
    }


def _avg_trust(nodes: list) -> Optional[float]:
    vals = [n.trust_score for n in nodes if n.trust_score is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _summary_from(nodes: list[WorkforceNode]) -> dict:
    by_type: dict[str, int] = {}
    cost_by_type: dict[str, float] = {}
    # A worker with no salary on record contributes nothing to a total and is
    # counted as unpriced, rather than silently costing zero or an invented
    # $120,000. Same for trust: unscored is not a low score.
    unpriced = sum(1 for n in nodes if n.cost_annual is None)
    unscored = sum(1 for n in nodes if n.trust_score is None)
    for n in nodes:
        by_type[n.type] = by_type.get(n.type, 0) + 1
        if n.cost_annual is not None:
            cost_by_type[n.type] = round(cost_by_type.get(n.type, 0.0) + n.cost_annual)
    total_cost = round(sum(n.cost_annual for n in nodes if n.cost_annual is not None))
    trust_vals = [n.trust_score for n in nodes if n.trust_score is not None]
    ai_nodes = [n for n in nodes if n.type in ("ai_agent", "bot")]
    human_nodes = [n for n in nodes if n.type == "human"]
    return {
        "total_workforce": len(nodes),
        "headcount_by_type": by_type,
        "cost_by_type": cost_by_type,
        "total_workforce_cost": total_cost,
        "workers_without_a_cost": unpriced,
        "workers_without_a_trust_score": unscored,
        "avg_trust": round(sum(trust_vals) / len(trust_vals), 1) if trust_vals else None,
        "avg_trust_humans": _avg_trust(human_nodes),
        "avg_trust_ai": _avg_trust(ai_nodes),
        "ai_agent_count": sum(1 for n in nodes if n.type == "ai_agent"),
        "bot_count": sum(1 for n in nodes if n.type == "bot"),
        "human_count": len(human_nodes),
        "contractor_count": sum(1 for n in nodes if n.type == "contractor"),
        "high_risk_nodes": [n.to_dict() for n in sorted(nodes, key=lambda x: -x.risk_score) if n.risk_score >= 60][:5],
    }


async def summary(db, org_id: str) -> dict:
    humans = await _humans_for_org(db, org_id)
    wf = build_workforce(humans)
    out = _summary_from(wf["nodes"])
    out["as_of"] = datetime.now(timezone.utc).isoformat()
    return out
