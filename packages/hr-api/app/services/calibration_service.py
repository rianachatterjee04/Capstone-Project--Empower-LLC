"""9-Box Performance x Potential calibration service.

The 9-box is the classic manager-calibration tool: each employee is placed on a
3x3 grid (performance on one axis, potential on the other), then managers meet to
calibrate placements to reduce rater bias.

WHAT CHANGED (real, not demo):
  * Placements persist to ``nine_box_placements`` (migration 20260722) via the
    sync->async bridge in ``app.services._hr_persistence`` — no more losing them
    on restart, and no more fake ``emp-5`` seeds.
  * The **performance axis is derived live** from each employee's latest finalized
    ``performance_reviews.rating`` (status completed/calibrated), joined on
    employee. Managers input only **potential** (+ rationale); performance is not
    hand-typed.
  * When performance AND potential are both high (3/3), the employee enters a
    **succession pool** exposed via ``succession_pool`` /
    ``succession_overlay`` — consumed by talent_marketplace and org_graph in
    place of their old hardcoded lists.

Fail-soft: if the DB is unreachable the service falls back to the legacy
in-process demo placements so the page still renders and the app still boots.
"""
from __future__ import annotations

import re
import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from app.services import _hr_persistence as _p

# ---------------------------------------------------------------------------
# 9-box semantics
# ---------------------------------------------------------------------------
# (perf, pot) -> cell label and standard talent-management interpretation.
NINEBOX_CELLS = {
    (1, 1): ("under-performer",         "Performance + potential both below bar — manage out or coach hard."),
    (1, 2): ("inconsistent-player",     "Doing the job but not stretching — clarify expectations."),
    (1, 3): ("high-potential / low-perf", "Talented but mis-deployed — investigate role fit before deciding."),
    (2, 1): ("solid-but-stuck",         "Reliable contributor; growth flatlined."),
    (2, 2): ("core-player",             "Healthy zone. Most of the org should be here."),
    (2, 3): ("future-leader",           "Ready for a stretch assignment — invest."),
    (3, 1): ("specialist",              "Top performer at this level; not interested in growth — protect and pay well."),
    (3, 2): ("high-impact",             "Top quartile + still climbing — succession candidate."),
    (3, 3): ("star",                    "Top-right cell — succession plan and retention risk both elevated."),
}


@dataclass
class NineBoxPlacement:
    id: str
    org_id: str
    employee_id: str
    employee_name: str
    team: str
    manager_id: str
    manager_name: str
    performance: int             # 1=below | 2=meeting | 3=exceeding  (derived from reviews)
    potential: int               # 1=limited | 2=growth | 3=high      (manager input)
    rationale: str = ""
    risk_flags: list[str] = field(default_factory=list)
    promotion_ready: bool = False
    placed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def cell_key(self) -> tuple[int, int]:
        return (self.performance, self.potential)

    def to_dict(self) -> dict:
        label, interpretation = NINEBOX_CELLS.get(self.cell_key, ("unknown", ""))
        return {
            **self.__dict__,
            "cell_key": list(self.cell_key),
            "cell_label": label,
            "cell_interpretation": interpretation,
        }


# ---------------------------------------------------------------------------
# In-process store — FALLBACK ONLY (used when the DB is unreachable)
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_placements: dict[str, dict[str, NineBoxPlacement]] = {}  # org_id -> placement_id -> p


_DEMO_PLACEMENTS = [
    # (emp_id, name, team, mgr_id, mgr_name, perf, pot, rationale)
    ("emp-2", "Atiman Rao",   "Atlas",   "emp-1", "Sarah Chen", 3, 3, "Owns validation pipeline end-to-end. Surfaces stretch problems unprompted."),
    ("emp-3", "Priya N",      "Helios",  "emp-1", "Sarah Chen", 3, 2, "Strong eng manager candidate; mentorship signal strong."),
    ("emp-4", "Marcus Patel", "Aurora",  "emp-1", "Sarah Chen", 2, 2, "Steady core PM; clear roadmap thinking; not chasing director track."),
    ("emp-5", "Mia O.",        "Nova",    "emp-1", "Sarah Chen", 3, 3, "Star designer; succession candidate for design lead."),
    ("emp-6", "Jordan P.",    "Vega",    "emp-1", "Sarah Chen", 2, 3, "Exceeded quota in Q1+Q2; ready for senior AE stretch."),
    ("emp-7", "Dana C.",      "Atlas",   "emp-1", "Sarah Chen", 3, 1, "Top-tier IC, content at this scope. Protect via comp + autonomy."),
    ("emp-8", "Robin T.",     "Aurora",  "emp-1", "Sarah Chen", 2, 2, "Steady data lead; consistent output."),
]


def _ensure_demo_seed(org_id: str) -> None:
    with _lock:
        if org_id not in _placements:
            _placements[org_id] = {}
            for eid, name, team, mid, mname, perf, pot, why in _DEMO_PLACEMENTS:
                pid = str(uuid.uuid4())
                p = NineBoxPlacement(
                    id=pid, org_id=org_id, employee_id=eid, employee_name=name, team=team,
                    manager_id=mid, manager_name=mname, performance=perf, potential=pot,
                    rationale=why, promotion_ready=(perf == 3 and pot >= 2),
                )
                _placements[org_id][pid] = p


# ---------------------------------------------------------------------------
# Bias detection helpers
# ---------------------------------------------------------------------------
_GENDERED_PATTERNS = [
    (re.compile(r"\b(aggressive|abrasive|emotional|nurturing|bossy|shrill|hysterical)\b", re.IGNORECASE),
     "gendered language detected"),
    (re.compile(r"\b(too\s+(?:assertive|quiet|loud|nice|harsh))\b", re.IGNORECASE),
     "'too X' phrasing — often biased"),
    (re.compile(r"\b(young|old|fresh|junior\s+sounding|seasoned)\b", re.IGNORECASE),
     "age-coded language"),
]


def detect_language_bias(text: str) -> list[str]:
    out: list[str] = []
    if not text:
        return out
    for pattern, note in _GENDERED_PATTERNS:
        if pattern.search(text):
            out.append(note)
    return out


# ---------------------------------------------------------------------------
# Review-derived performance axis
# ---------------------------------------------------------------------------
def _perf_from_rating(rating: Optional[int]) -> int:
    """Map a 1-5 review rating onto the 9-box 1-3 performance band."""
    if rating is None:
        return 2
    if rating <= 2:
        return 1
    if rating == 3:
        return 2
    return 3


def _use_db() -> bool:
    return _p.db_available()


def _review_axis(org_id: str) -> dict[str, dict]:
    """employee_id(str) -> {performance, rating, employee_name, team, job_title,
    tenure_years, manager_id, manager_name} built from the latest finalized
    performance review per employee."""
    rows = _p.q(
        "SELECT DISTINCT ON (pr.employee_id) pr.employee_id, pr.rating, "
        "e.legal_name, e.department, e.job_title, e.start_date, e.manager_employee_id "
        "FROM performance_reviews pr JOIN employees e ON e.id = pr.employee_id "
        "WHERE pr.org_id = CAST(:o AS uuid) AND pr.status IN ('completed','calibrated') "
        "AND pr.rating IS NOT NULL "
        "ORDER BY pr.employee_id, COALESCE(pr.finalized_at, pr.created_at) DESC, pr.cycle DESC",
        o=org_id)
    # Resolve manager names from the org's employee roster.
    name_by_id = {str(r["id"]): r["legal_name"]
                  for r in _p.q("SELECT id, legal_name FROM employees WHERE org_id = CAST(:o AS uuid)", o=org_id)}
    today = date.today()
    out: dict[str, dict] = {}
    for r in rows:
        eid = str(r["employee_id"])
        rating = int(r["rating"]) if r["rating"] is not None else None
        mgr_id = str(r["manager_employee_id"]) if r["manager_employee_id"] else ""
        sd = r["start_date"]
        tenure = round((today - sd).days / 365.25, 1) if sd else 2.0
        out[eid] = {
            "performance": _perf_from_rating(rating),
            "rating": rating,
            "employee_name": r["legal_name"],
            "team": r["department"] or "",
            "job_title": r["job_title"] or "",
            "tenure_years": tenure,
            "manager_id": mgr_id,
            "manager_name": name_by_id.get(mgr_id, ""),
        }
    return out


# ---------------------------------------------------------------------------
# Placement persistence
# ---------------------------------------------------------------------------
def _placement_from_row(r: dict) -> NineBoxPlacement:
    placed = r["placed_at"]
    updated = r["updated_at"]
    return NineBoxPlacement(
        id=str(r["id"]), org_id=str(r["org_id"]), employee_id=r["employee_id"],
        employee_name=r["employee_name"], team=r["team"], manager_id=r["manager_id"],
        manager_name=r["manager_name"], performance=int(r["performance"]), potential=int(r["potential"]),
        rationale=r["rationale"], risk_flags=_p.json_load(r["risk_flags"]) or [],
        promotion_ready=bool(r["promotion_ready"]),
        placed_at=placed.isoformat() if hasattr(placed, "isoformat") else str(placed),
        updated_at=updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
    )


def _db_stored_placements(org_id: str) -> dict[str, NineBoxPlacement]:
    rows = _p.q("SELECT * FROM nine_box_placements WHERE org_id = CAST(:o AS uuid)", o=org_id)
    return {p.employee_id: p for p in (_placement_from_row(r) for r in rows)}


def _db_list_placements(org_id: str) -> list[NineBoxPlacement]:
    """Merge review-derived performance with stored manager potential.

    Every employee with a finalized review appears (performance from the review,
    potential from a stored placement or the neutral default 2). Manually placed
    employees who have no finalized review keep their stored snapshot.
    """
    review = _review_axis(org_id)
    stored = _db_stored_placements(org_id)
    out: dict[str, NineBoxPlacement] = {}

    for eid, rv in review.items():
        sp = stored.get(eid)
        potential = sp.potential if sp else 2
        performance = rv["performance"]  # authoritative: from the latest finalized review
        p = NineBoxPlacement(
            id=sp.id if sp else str(uuid.uuid4()),
            org_id=org_id,
            employee_id=eid,
            employee_name=(sp.employee_name if sp and sp.employee_name else rv["employee_name"]),
            team=(sp.team if sp and sp.team else rv["team"]),
            manager_id=(sp.manager_id if sp and sp.manager_id else rv["manager_id"]),
            manager_name=(sp.manager_name if sp and sp.manager_name else rv["manager_name"]),
            performance=performance,
            potential=potential,
            rationale=sp.rationale if sp else "",
            risk_flags=sp.risk_flags if sp else [],
            promotion_ready=(performance == 3 and potential >= 2),
            placed_at=sp.placed_at if sp else datetime.now(timezone.utc).isoformat(),
            updated_at=sp.updated_at if sp else datetime.now(timezone.utc).isoformat(),
        )
        out[eid] = p

    # Stored placements without a finalized review — keep the manager's snapshot.
    for eid, sp in stored.items():
        if eid not in out:
            out[eid] = sp

    items = list(out.values())
    items.sort(key=lambda p: (p.team, -p.performance, -p.potential))
    return items


# ---------------------------------------------------------------------------
# Public surface (unchanged signatures)
# ---------------------------------------------------------------------------
def upsert_placement(
    org_id: str,
    *,
    employee_id: str,
    employee_name: str,
    team: str,
    manager_id: str,
    manager_name: str,
    performance: int,
    potential: int,
    rationale: str = "",
) -> NineBoxPlacement:
    potential = max(1, min(3, int(potential)))
    passed_perf = max(1, min(3, int(performance)))
    risk = detect_language_bias(rationale)

    if _use_db():
        try:
            review = _review_axis(org_id)
            rv = review.get(str(employee_id))
            # Manager inputs only potential; performance comes from the review when we have one.
            perf = rv["performance"] if rv else passed_perf
            name = employee_name or (rv["employee_name"] if rv else "")
            tm = team or (rv["team"] if rv else "")
            mid = manager_id or (rv["manager_id"] if rv else "")
            mname = manager_name or (rv["manager_name"] if rv else "")
            promo = (perf == 3 and potential >= 2)
            pid = str(uuid.uuid4())

            async def _op(sess):
                await sess.execute(_p.text(
                    "INSERT INTO nine_box_placements "
                    "(id, org_id, employee_id, employee_name, team, manager_id, manager_name, performance, potential, rationale, risk_flags, promotion_ready, updated_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :eid, :name, :team, :mid, :mname, :perf, :pot, :rat, CAST(:risk AS jsonb), :promo, now()) "
                    "ON CONFLICT (org_id, employee_id) DO UPDATE SET "
                    "employee_name = EXCLUDED.employee_name, team = EXCLUDED.team, manager_id = EXCLUDED.manager_id, "
                    "manager_name = EXCLUDED.manager_name, performance = EXCLUDED.performance, potential = EXCLUDED.potential, "
                    "rationale = EXCLUDED.rationale, risk_flags = EXCLUDED.risk_flags, promotion_ready = EXCLUDED.promotion_ready, "
                    "updated_at = now()"),
                    {"id": pid, "org": org_id, "eid": str(employee_id), "name": name, "team": tm,
                     "mid": mid, "mname": mname, "perf": perf, "pot": potential, "rat": rationale,
                     "risk": _p.json_dump(risk), "promo": promo})

            _p.tx(_op)
            # Return the merged/derived placement.
            for p in _db_list_placements(org_id):
                if p.employee_id == str(employee_id):
                    return p
            return NineBoxPlacement(
                id=pid, org_id=org_id, employee_id=str(employee_id), employee_name=name, team=tm,
                manager_id=mid, manager_name=mname, performance=perf, potential=potential,
                rationale=rationale, risk_flags=risk, promotion_ready=promo,
            )
        except Exception as e:
            _p.note_fallback("calibration.upsert_placement", e)

    # In-memory fallback
    _ensure_demo_seed(org_id)
    with _lock:
        existing = next(
            (p for p in _placements.get(org_id, {}).values() if p.employee_id == employee_id), None)
        if existing:
            existing.team = team
            existing.manager_id = manager_id
            existing.manager_name = manager_name
            existing.performance = passed_perf
            existing.potential = potential
            existing.rationale = rationale
            existing.risk_flags = risk
            existing.promotion_ready = (passed_perf == 3 and potential >= 2)
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            return existing
        pid = str(uuid.uuid4())
        p = NineBoxPlacement(
            id=pid, org_id=org_id, employee_id=employee_id, employee_name=employee_name, team=team,
            manager_id=manager_id, manager_name=manager_name, performance=passed_perf, potential=potential,
            rationale=rationale, risk_flags=risk, promotion_ready=(passed_perf == 3 and potential >= 2),
        )
        _placements[org_id][pid] = p
        return p


def list_placements(org_id: str) -> list[NineBoxPlacement]:
    if _use_db():
        try:
            return _db_list_placements(org_id)
        except Exception as e:
            _p.note_fallback("calibration.list_placements", e)
    _ensure_demo_seed(org_id)
    with _lock:
        items = list(_placements.get(org_id, {}).values())
    items.sort(key=lambda p: (p.team, -p.performance, -p.potential))
    return items


def grid_snapshot(org_id: str) -> dict:
    placements = list_placements(org_id)
    grid: dict[str, list[dict]] = {}
    for perf in (1, 2, 3):
        for pot in (1, 2, 3):
            grid[f"{perf}-{pot}"] = []
    for p in placements:
        grid[f"{p.performance}-{p.potential}"].append({
            "id": p.id,
            "employee_id": p.employee_id,
            "employee_name": p.employee_name,
            "team": p.team,
            "manager_name": p.manager_name,
            "promotion_ready": p.promotion_ready,
            "risk_flags": p.risk_flags,
        })
    return {
        "grid": grid,
        "cells": {f"{k[0]}-{k[1]}": {"label": v[0], "interpretation": v[1]} for k, v in NINEBOX_CELLS.items()},
        "n_placements": len(placements),
    }


def calibrate_managers(org_id: str) -> dict:
    """Surface rater behaviour patterns across managers."""
    placements = list_placements(org_id)
    by_mgr: dict[str, list[NineBoxPlacement]] = {}
    for p in placements:
        by_mgr.setdefault(p.manager_id, []).append(p)

    out: list[dict] = []
    for mgr_id, ps in by_mgr.items():
        if not ps:
            continue
        perfs = [p.performance for p in ps]
        pots = [p.potential for p in ps]
        avg_perf = round(statistics.mean(perfs), 2)
        avg_pot = round(statistics.mean(pots), 2)
        spread_perf = max(perfs) - min(perfs)
        spread_pot = max(pots) - min(pots)

        bias_flags: list[str] = []
        if avg_perf >= 2.8:
            bias_flags.append("Possible leniency bias — most reports rated at top performance band.")
        elif avg_perf <= 1.4:
            bias_flags.append("Possible severity bias — most reports rated below performance bar.")
        if spread_perf == 0 and len(ps) >= 3:
            bias_flags.append("Centrality bias — all reports placed in the same performance row.")
        if spread_pot == 0 and len(ps) >= 3:
            bias_flags.append("Centrality bias — all reports placed in the same potential column.")
        # Halo effect — every report on the diagonal (perf == pot)
        if len(ps) >= 4 and all(p.performance == p.potential for p in ps):
            bias_flags.append("Halo effect — performance and potential perfectly correlated for every report. Probe the calibration.")

        # Language bias across reports
        lang_flags = sum(len(p.risk_flags) for p in ps)
        if lang_flags:
            bias_flags.append(f"{lang_flags} biased-language flag(s) detected in rationale text.")

        out.append({
            "manager_id": mgr_id,
            "manager_name": ps[0].manager_name,
            "n_reports": len(ps),
            "avg_performance": avg_perf,
            "avg_potential": avg_pot,
            "spread_performance": spread_perf,
            "spread_potential": spread_pot,
            "bias_flags": bias_flags,
        })
    out.sort(key=lambda r: -len(r["bias_flags"]))
    return {"managers": out}


def highlights(org_id: str) -> dict:
    """Surface promotion-ready + retention-risk lists."""
    placements = list_placements(org_id)
    promo_ready = [p.to_dict() for p in placements if p.promotion_ready]
    stars = [p.to_dict() for p in placements if p.cell_key == (3, 3)]
    retention_risk = [
        p.to_dict() for p in placements
        if p.cell_key in ((3, 3), (3, 2))  # top performers, biggest flight risk
    ]
    underperformers = [
        p.to_dict() for p in placements
        if p.cell_key == (1, 1)
    ]
    return {
        "promotion_ready": promo_ready,
        "stars": stars,
        "retention_risk": retention_risk,
        "underperformers": underperformers,
    }


# ---------------------------------------------------------------------------
# Succession pool — fed by high/high (3/3) placements. Consumed by
# talent_marketplace_service.succession_candidates_for_role and org_graph_service
# in place of their old hardcoded lists.
# ---------------------------------------------------------------------------
def _is_succession(p: NineBoxPlacement) -> bool:
    """Both axes high => succession candidate."""
    return p.performance >= 3 and p.potential >= 3


def succession_pool(org_id: str) -> list[dict]:
    """Employees who are both high-performance and high-potential, shaped for the
    talent marketplace matcher: {id, name, skills, performance_rating, tenure_years}.

    Skills are inferred from the employee's role profile (best-effort);
    performance_rating is the real 1-5 review rating where available. Returns []
    when nothing qualifies (callers may then fall back to their own demo pool).
    """
    try:
        placements = list_placements(org_id)
    except Exception:
        return []
    pool_ids = [p.employee_id for p in placements if _is_succession(p)]
    if not pool_ids:
        return []

    # Enrich from the review axis (rating, job_title, tenure) when we have it.
    review = {}
    if _use_db():
        try:
            review = _review_axis(org_id)
        except Exception:
            review = {}

    try:  # lazy: learning_service is also imported by talent_marketplace
        from app.services.learning_service import required_skills_for
    except Exception:
        required_skills_for = None  # type: ignore

    pool: list[dict] = []
    for p in placements:
        if not _is_succession(p):
            continue
        rv = review.get(p.employee_id, {})
        job_title = rv.get("job_title") or ""
        skills: list[str] = []
        if required_skills_for and job_title:
            try:
                skills = required_skills_for(job_title)
            except Exception:
                skills = []
        rating = rv.get("rating")
        perf_rating = float(rating) if rating is not None else (3.0 + (p.performance - 1) * 1.0)
        pool.append({
            "id": p.employee_id,
            "name": p.employee_name,
            "skills": skills,
            "performance_rating": perf_rating,
            "tenure_years": float(rv.get("tenure_years") or 2.0),
        })
    return pool


def succession_overlay(org_id: str) -> dict[str, str]:
    """employee_name -> succession status ('ready' | 'groom' | 'none') derived
    from live placements. Used by org_graph_service to replace its hardcoded
    _SUCCESSION_OVERLAY. Empty dict => callers keep their own default overlay."""
    try:
        placements = list_placements(org_id)
    except Exception:
        return {}
    overlay: dict[str, str] = {}
    for p in placements:
        if _is_succession(p):
            overlay[p.employee_name] = "ready"
        elif p.promotion_ready or p.potential >= 3:
            overlay[p.employee_name] = "groom"
    return overlay
