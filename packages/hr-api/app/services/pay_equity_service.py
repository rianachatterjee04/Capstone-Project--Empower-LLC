"""Pay Equity analysis + remediation (EU Pay Transparency Directive readiness).

NET-NEW P0 differentiator. Given employees with compensation + attributes
(gender / other protected class, level, job-family, role, location, tenure) this
service computes:

  * raw pay gaps  (unadjusted mean difference between a protected group and the
    reference group)
  * adjusted pay gaps  (a *deterministic, explainable* regression-style control
    for level / job-family / location / tenure) — see the methodology note below
  * gaps by segment  (by protected group, and by job-family × level "job
    category")
  * an EU-directive readiness check  (flag any job category whose *unexplained*
    (adjusted) gap exceeds the directive's 5% threshold)
  * remediation recommendations  (a per-employee suggested adjustment + the total
    remediation budget required to close every flagged cohort to the threshold)

METHODOLOGY — adjusted gap (deterministic, hand-checkable)
----------------------------------------------------------
A full OLS regression on *categorical* controls is mathematically identical to
comparing group means *within control cells*. We use that equivalence so every
number is explainable and hand-checkable (no opaque coefficients):

  1. Pick the reference group R for the protected attribute (default: the group
     with the highest mean pay — the advantaged group; deterministic, ties
     broken alphabetically). Every other value of the attribute is a protected
     group G.
  2. Partition all employees into *control cohorts* keyed by the applied
     controls (level × job_family × location × tenure_band). Cohorts are the
     "like-for-like" comparison cells.
  3. RAW gap$  = mean(R) - mean(G) over the whole population.
     RAW gap%  = raw_gap$ / mean(R).
  4. ADJUSTED: for every cohort c that contains *both* an R member and a G
     member, the within-cohort gap is  gap_c = mean_R(c) - mean_G(c).  Cohorts
     lacking a comparison group are dropped and reported as
     "insufficient_comparison" (never silently averaged in).
     ADJUSTED gap$ = Σ gap_c · n_G(c)  /  Σ n_G(c)         (weighted by protected headcount)
     ADJUSTED gap% = adjusted_gap$ / (Σ mean_R(c) · n_G(c) / Σ n_G(c))
  The adjusted gap is the portion of the raw gap that remains *after* legitimate
  composition differences (protected group concentrated in lower levels /
  cheaper locations / shorter tenure) are controlled for. That residual is the
  "unexplained" gap the directive cares about.

Every result carries `controls_applied` so the analysis is auditable.

REMEDIATION
-----------
To close a cohort to a target threshold t, the floor for a protected-group
member is  floor_c = mean_R(c) · (1 - t).  Any protected member paid below their
cohort floor is raised to it; the suggested adjustment is  floor_c - salary.
Summing the adjustments gives the remediation budget. This deterministically
drives every comparable cohort's gap to ≤ t.

The module is pure/deterministic and fail-soft: empty or single-group inputs
return zeroed analysis with a reason, never an exception.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------
DEFAULT_CONTROLS = ("level", "job_family", "location", "tenure_band")
DEFAULT_THRESHOLD = 0.05  # EU Pay Transparency Directive: 5% unexplained gap


@dataclass
class PEEmployee:
    id: str
    name: str
    salary: float
    gender: str = "unknown"           # male | female | nonbinary | unknown
    ethnicity: Optional[str] = None   # optional second protected class
    level: str = "L?"                 # e.g. L3, L4 / IC2 / M1
    job_family: str = "General"       # Engineering, Sales, Product, ...
    role: str = ""
    location: str = "Remote"
    tenure_years: float = 0.0
    currency: str = "USD"

    @property
    def tenure_band(self) -> str:
        t = self.tenure_years or 0.0
        if t < 2:
            return "0-2y"
        if t < 5:
            return "2-5y"
        return "5y+"

    def attr(self, name: str) -> str:
        return str(getattr(self, name, "") or "")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tenure_band"] = self.tenure_band
        return d


def _r2(x: float) -> float:
    return round(float(x or 0.0), 2)


def _r4(x: float) -> float:
    return round(float(x or 0.0), 4)


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _cohort_key(emp: PEEmployee, controls: tuple[str, ...]) -> tuple:
    return tuple(emp.attr(c) if c != "tenure_band" else emp.tenure_band for c in controls)


def _pick_reference(employees: list[PEEmployee], attr: str) -> Optional[str]:
    """Reference group = the attribute value with the highest mean pay
    (advantaged group). Deterministic; ties broken alphabetically."""
    groups: dict[str, list[float]] = {}
    for e in employees:
        v = e.attr(attr)
        if not v or v == "unknown":
            continue
        groups.setdefault(v, []).append(e.salary)
    if len(groups) < 2:
        return None
    # highest mean first, then alphabetical for determinism
    ordered = sorted(groups.items(), key=lambda kv: (-_mean(kv[1]), kv[0]))
    return ordered[0][0]


# ---------------------------------------------------------------------------
# Core gap math (pure — golden-vector surface)
# ---------------------------------------------------------------------------
def raw_gap(employees: list[PEEmployee], attr: str, reference: str, group: str) -> dict:
    r = [e.salary for e in employees if e.attr(attr) == reference]
    g = [e.salary for e in employees if e.attr(attr) == group]
    mean_r, mean_g = _mean(r), _mean(g)
    gap_abs = mean_r - mean_g
    gap_pct = (gap_abs / mean_r) if mean_r else 0.0
    return {
        "reference_group": reference,
        "group": group,
        "reference_mean": _r2(mean_r),
        "group_mean": _r2(mean_g),
        "reference_n": len(r),
        "group_n": len(g),
        "gap_abs": _r2(gap_abs),
        "gap_pct": _r4(gap_pct),
    }


def adjusted_gap(
    employees: list[PEEmployee],
    attr: str,
    reference: str,
    group: str,
    controls: tuple[str, ...] = DEFAULT_CONTROLS,
) -> dict:
    """Adjusted gap via like-for-like control cohorts (saturated categorical
    model). Returns the weighted residual gap plus the per-cohort breakdown so
    the number is fully explainable."""
    cohorts: dict[tuple, dict[str, list[float]]] = {}
    for e in employees:
        v = e.attr(attr)
        if v not in (reference, group):
            continue
        key = _cohort_key(e, controls)
        bucket = cohorts.setdefault(key, {"R": [], "G": []})
        bucket["R" if v == reference else "G"].append(e.salary)

    comparable: list[dict] = []
    dropped: list[dict] = []
    num_abs = 0.0
    num_ref = 0.0
    den = 0.0  # Σ n_G over comparable cohorts
    for key, b in sorted(cohorts.items(), key=lambda kv: str(kv[0])):
        n_r, n_g = len(b["R"]), len(b["G"])
        cohort_label = dict(zip(controls, key))
        if n_r == 0 or n_g == 0:
            dropped.append({
                "cohort": cohort_label,
                "reference_n": n_r,
                "group_n": n_g,
                "reason": "insufficient_comparison",
            })
            continue
        mean_r, mean_g = _mean(b["R"]), _mean(b["G"])
        gap_c = mean_r - mean_g
        comparable.append({
            "cohort": cohort_label,
            "reference_mean": _r2(mean_r),
            "group_mean": _r2(mean_g),
            "reference_n": n_r,
            "group_n": n_g,
            "gap_abs": _r2(gap_c),
            "gap_pct": _r4(gap_c / mean_r) if mean_r else 0.0,
            "weight_group_n": n_g,
        })
        num_abs += gap_c * n_g
        num_ref += mean_r * n_g
        den += n_g

    adj_abs = (num_abs / den) if den else 0.0
    weighted_ref_mean = (num_ref / den) if den else 0.0
    adj_pct = (adj_abs / weighted_ref_mean) if weighted_ref_mean else 0.0
    return {
        "reference_group": reference,
        "group": group,
        "controls_applied": list(controls),
        "adjusted_gap_abs": _r2(adj_abs),
        "adjusted_gap_pct": _r4(adj_pct),
        "weighted_reference_mean": _r2(weighted_ref_mean),
        "comparable_cohorts": comparable,
        "dropped_cohorts": dropped,
        "group_n_compared": int(den),
    }


def _job_category(emp: PEEmployee) -> str:
    return f"{emp.job_family} · {emp.level}"


def category_gaps(
    employees: list[PEEmployee],
    attr: str,
    reference: str,
    group: str,
    threshold: float = DEFAULT_THRESHOLD,
    controls: tuple[str, ...] = DEFAULT_CONTROLS,
) -> list[dict]:
    """EU-directive job-category view: adjusted gap per job_family × level, with
    a >threshold flag. Controls within a category collapse to location × tenure."""
    inner_controls = tuple(c for c in controls if c not in ("job_family", "level"))
    cats: dict[str, list[PEEmployee]] = {}
    for e in employees:
        if e.attr(attr) in (reference, group):
            cats.setdefault(_job_category(e), []).append(e)
    out: list[dict] = []
    for cat, emps in sorted(cats.items()):
        adj = adjusted_gap(emps, attr, reference, group, inner_controls)
        rawg = raw_gap(emps, attr, reference, group)
        flagged = adj["adjusted_gap_pct"] > threshold and adj["group_n_compared"] > 0
        out.append({
            "job_category": cat,
            "headcount": len(emps),
            "raw_gap_pct": rawg["gap_pct"],
            "adjusted_gap_pct": adj["adjusted_gap_pct"],
            "adjusted_gap_abs": adj["adjusted_gap_abs"],
            "group_n_compared": adj["group_n_compared"],
            "controls_applied": adj["controls_applied"],
            "exceeds_threshold": flagged,
            "threshold": threshold,
        })
    return out


def analyze(
    employees: list[PEEmployee],
    attr: str = "gender",
    reference: Optional[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
    controls: tuple[str, ...] = DEFAULT_CONTROLS,
) -> dict:
    """Full org-wide analysis for one protected attribute."""
    if not employees:
        return {"attribute": attr, "available": False, "reason": "no employees", "groups": []}
    ref = reference or _pick_reference(employees, attr)
    if not ref:
        return {
            "attribute": attr, "available": False,
            "reason": "need at least two groups on this attribute to compute a gap",
            "groups": [],
        }
    values = sorted({e.attr(attr) for e in employees if e.attr(attr) and e.attr(attr) != "unknown"})
    groups_out: list[dict] = []
    for g in values:
        if g == ref:
            continue
        rawg = raw_gap(employees, attr, ref, g)
        adj = adjusted_gap(employees, attr, ref, g, controls)
        groups_out.append({
            "group": g,
            "raw_gap_pct": rawg["gap_pct"],
            "raw_gap_abs": rawg["gap_abs"],
            "adjusted_gap_pct": adj["adjusted_gap_pct"],
            "adjusted_gap_abs": adj["adjusted_gap_abs"],
            "explained_pct": _r4(rawg["gap_pct"] - adj["adjusted_gap_pct"]),
            "reference_mean": rawg["reference_mean"],
            "group_mean": rawg["group_mean"],
            "reference_n": rawg["reference_n"],
            "group_n": rawg["group_n"],
            "exceeds_threshold": adj["adjusted_gap_pct"] > threshold,
            "cohort_detail": adj,
        })
    # by job category (only meaningful vs the primary protected group = largest non-ref)
    primary_group = None
    if groups_out:
        primary_group = max(groups_out, key=lambda x: x["group_n"])["group"]
    cats = category_gaps(employees, attr, ref, primary_group, threshold, controls) if primary_group else []
    flagged_cats = [c for c in cats if c["exceeds_threshold"]]
    return {
        "attribute": attr,
        "available": True,
        "reference_group": ref,
        "threshold": threshold,
        "controls_applied": list(controls),
        "headcount": len(employees),
        "groups": groups_out,
        "job_categories": cats,
        "primary_protected_group": primary_group,
        "n_flagged_categories": len(flagged_cats),
        "directive_ready": len(flagged_cats) == 0,
    }


def remediation_plan(
    employees: list[PEEmployee],
    attr: str = "gender",
    reference: Optional[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
    controls: tuple[str, ...] = DEFAULT_CONTROLS,
) -> dict:
    """Per-employee suggested adjustments + total budget to close every
    comparable cohort to `threshold`. Deterministic."""
    if not employees:
        return {"attribute": attr, "available": False, "reason": "no employees",
                "adjustments": [], "total_budget": 0.0}
    ref = reference or _pick_reference(employees, attr)
    if not ref:
        return {"attribute": attr, "available": False,
                "reason": "need at least two groups", "adjustments": [], "total_budget": 0.0}

    # cohort reference means over the control cells
    cohorts: dict[tuple, list[float]] = {}
    for e in employees:
        if e.attr(attr) == ref:
            cohorts.setdefault(_cohort_key(e, controls), []).append(e.salary)
    cohort_ref_mean = {k: _mean(v) for k, v in cohorts.items()}

    adjustments: list[dict] = []
    total = 0.0
    for e in employees:
        v = e.attr(attr)
        if v == ref or v == "unknown" or not v:
            continue
        key = _cohort_key(e, controls)
        ref_mean = cohort_ref_mean.get(key)
        if not ref_mean:
            continue  # no reference peer in this cohort → cannot justify a raise
        floor = ref_mean * (1 - threshold)
        if e.salary < floor - 0.005:
            adj = floor - e.salary
            total += adj
            adjustments.append({
                "employee_id": e.id,
                "name": e.name,
                "group": v,
                "cohort": dict(zip(controls, key)),
                "current_salary": _r2(e.salary),
                "cohort_reference_mean": _r2(ref_mean),
                "target_floor": _r2(floor),
                "suggested_adjustment": _r2(adj),
                "new_salary": _r2(floor),
                "pct_increase": _r4(adj / e.salary) if e.salary else 0.0,
            })
    adjustments.sort(key=lambda a: -a["suggested_adjustment"])
    return {
        "attribute": attr,
        "available": True,
        "reference_group": ref,
        "threshold": threshold,
        "controls_applied": list(controls),
        "n_employees_adjusted": len(adjustments),
        "total_budget": _r2(total),
        "adjustments": adjustments,
    }


def employee_position(
    employees: list[PEEmployee], employee_id: str,
    attr: str = "gender", controls: tuple[str, ...] = DEFAULT_CONTROLS,
) -> Optional[dict]:
    """One employee's position vs their like-for-like cohort peers + band."""
    me = next((e for e in employees if e.id == employee_id), None)
    if not me:
        return None
    key = _cohort_key(me, controls)
    peers = [e for e in employees if _cohort_key(e, controls) == key]
    peer_salaries = sorted(e.salary for e in peers)
    peer_mean = _mean(peer_salaries)
    below = sum(1 for s in peer_salaries if s < me.salary)
    percentile = _r4(below / len(peer_salaries)) if peer_salaries else 0.0
    ref = _pick_reference(employees, attr)
    ref_peers = [e.salary for e in peers if ref and e.attr(attr) == ref]
    ref_mean = _mean(ref_peers) if ref_peers else None
    return {
        "employee": me.to_dict(),
        "cohort": dict(zip(controls, key)),
        "cohort_size": len(peers),
        "cohort_mean": _r2(peer_mean),
        "cohort_min": _r2(peer_salaries[0]) if peer_salaries else 0.0,
        "cohort_max": _r2(peer_salaries[-1]) if peer_salaries else 0.0,
        "percentile_in_cohort": percentile,
        "compa_ratio_vs_cohort": _r4(me.salary / peer_mean) if peer_mean else None,
        "reference_group": ref,
        "reference_group_mean": _r2(ref_mean) if ref_mean is not None else None,
        "gap_vs_reference_abs": _r2(ref_mean - me.salary) if ref_mean is not None else None,
        "controls_applied": list(controls),
    }


# ---------------------------------------------------------------------------
# Org-scoped in-process store (mirrors goals/recognition pattern)
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_store: dict[str, list[PEEmployee]] = {}
_seeded: set[str] = set()


def _seed(org_id: str) -> None:
    """Realistic, day-one-alive dataset with a genuine, controllable gap."""
    rows: list[tuple] = [
        # name, salary, gender, ethnicity, level, family, role, location, tenure
        ("Avery Chen", 175000, "male", "asian", "L5", "Engineering", "Staff Eng", "SF", 6.0),
        ("Jordan Blake", 172000, "male", "white", "L5", "Engineering", "Staff Eng", "SF", 5.5),
        ("Riya Kapoor", 158000, "female", "asian", "L5", "Engineering", "Staff Eng", "SF", 5.0),
        ("Sam Okafor", 140000, "male", "black", "L4", "Engineering", "Senior Eng", "SF", 4.0),
        ("Diego Ramos", 138000, "male", "hispanic", "L4", "Engineering", "Senior Eng", "Remote", 3.5),
        ("Mei Lin", 128000, "female", "asian", "L4", "Engineering", "Senior Eng", "SF", 3.0),
        ("Grace Park", 126000, "female", "asian", "L4", "Engineering", "Senior Eng", "Remote", 3.5),
        ("Noah Fisher", 118000, "male", "white", "L3", "Engineering", "Eng", "Remote", 2.0),
        ("Priya Nair", 106000, "female", "asian", "L3", "Engineering", "Eng", "Remote", 2.5),
        ("Ana Sousa", 108000, "female", "hispanic", "L3", "Engineering", "Eng", "Austin", 2.0),
        ("Tom Reilly", 165000, "male", "white", "M2", "Sales", "Sales Manager", "NY", 5.0),
        ("Kevin Wright", 162000, "male", "black", "M2", "Sales", "Sales Manager", "NY", 4.5),
        ("Sofia Marin", 149000, "female", "hispanic", "M2", "Sales", "Sales Manager", "NY", 4.0),
        ("Jack Doyle", 122000, "male", "white", "IC3", "Sales", "AE", "NY", 3.0),
        ("Hana Suzuki", 111000, "female", "asian", "IC3", "Sales", "AE", "NY", 3.0),
        ("Leah Gold", 113000, "female", "white", "IC3", "Sales", "AE", "Austin", 2.5),
    ]
    _store[org_id] = [
        PEEmployee(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{org_id}:{name}")),
            name=name, salary=float(sal), gender=gen, ethnicity=eth,
            level=lvl, job_family=fam, role=role, location=loc, tenure_years=ten,
        )
        for (name, sal, gen, eth, lvl, fam, role, loc, ten) in rows
    ]


# Which orgs are looking at the shipped sample cohort rather than their own
# people. `set_employees` clears the flag, because at that point the analysis
# is about real employees.
_is_sample: set[str] = set()


def _ensure(org_id: str) -> list[PEEmployee]:
    with _lock:
        if org_id not in _seeded:
            _seed(org_id)
            _seeded.add(org_id)
            _is_sample.add(org_id)
        return _store.setdefault(org_id, [])


def uses_sample_cohort(org_id: str) -> bool:
    _ensure(org_id)
    return org_id in _is_sample


def set_employees(org_id: str, employees: list[PEEmployee]) -> None:
    with _lock:
        _store[org_id] = list(employees)
        _seeded.add(org_id)
        _is_sample.discard(org_id)


def list_employees(org_id: str) -> list[PEEmployee]:
    return list(_ensure(org_id))


# ---- org-scoped wrappers used by the router ----
def org_analysis(org_id: str, *, attr: str = "gender", threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Pay-gap analysis for an org, saying whose pay it analysed.

    THIS IS A REGULATORY CLAIM. The page renders "Headcount analysed 16",
    "Female vs Male — raw gap 16.2%, adjusted gap 8.8%, over threshold" and a
    "$32,825 remediation budget", under a header about EU Pay Transparency
    Directive readiness. For an organisation with one employee, every one of
    those numbers came from the sixteen-person cohort seeded by _seed().

    A fabricated gender pay gap is the most legally loaded thing this product
    could show someone. The maths is sound and worth demonstrating; the claim
    that it is about their company is what cannot stand.
    """
    out = analyze(_ensure(org_id), attr=attr, threshold=threshold)
    sample = uses_sample_cohort(org_id)
    out["cohort"] = {
        "is_sample": sample,
        "source": "sample_cohort" if sample else "employee_records",
        "note": (
            "This analysis ran on the sixteen-person illustrative cohort shipped "
            "with the product, not on your employees. The gaps, thresholds and "
            "remediation cost below are a worked example. Load your own "
            "compensation records with gender, level, job family, location and "
            "tenure to run it for real."
            if sample else
            "This analysis ran on your own compensation records."
        ),
        "needs": ([
            "salary per employee",
            "the protected attribute being analysed",
            "level, job family, location and tenure, to compute the adjusted gap",
        ] if sample else []),
    }
    return out


def org_employee_position(org_id: str, employee_id: str, *, attr: str = "gender") -> Optional[dict]:
    return employee_position(_ensure(org_id), employee_id, attr=attr)


def org_remediation(org_id: str, *, attr: str = "gender", threshold: float = DEFAULT_THRESHOLD) -> dict:
    return remediation_plan(_ensure(org_id), attr=attr, threshold=threshold)


def compliance_report(org_id: str, *, attr: str = "gender", threshold: float = DEFAULT_THRESHOLD) -> dict:
    """EU-Pay-Transparency-Directive-style compliance report."""
    emps = _ensure(org_id)
    an = analyze(emps, attr=attr, threshold=threshold)
    rem = remediation_plan(emps, attr=attr, threshold=threshold)
    flagged = [c for c in an.get("job_categories", []) if c.get("exceeds_threshold")]
    return {
        "framework": "EU Pay Transparency Directive (Directive (EU) 2023/970)",
        "reporting_threshold": threshold,
        "attribute": attr,
        "generated_note": (
            "AI-assisted pay-equity analysis. Adjusted gaps control for level, "
            "job-family, location and tenure. Any category with an unexplained "
            f"(adjusted) gap above {int(threshold*100)}% requires a joint pay "
            "assessment under the directive."
        ),
        "reference_group": an.get("reference_group"),
        "headcount": an.get("headcount", 0),
        "directive_ready": an.get("directive_ready", False),
        "n_flagged_categories": an.get("n_flagged_categories", 0),
        "flagged_categories": flagged,
        "remediation_budget": rem.get("total_budget", 0.0),
        "employees_requiring_adjustment": rem.get("n_employees_adjusted", 0),
        "controls_applied": an.get("controls_applied", list(DEFAULT_CONTROLS)),
        "disclaimer": (
            "This report is decision-support, not legal advice. Final pay-equity "
            "determinations and any objective-justification of gaps require human "
            "review by HR/Legal."
        ),
    }
