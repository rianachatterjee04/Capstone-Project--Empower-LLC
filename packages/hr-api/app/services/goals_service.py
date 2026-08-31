"""Goals & OKRs.

Lightweight OKR layer: cycle -> objectives -> key results, with optional
linked tasks.

Persistence: objectives + key results live in Postgres (tables ``objectives`` /
``key_results``, migration 20260722). The service functions stay synchronous
with identical signatures — they reach the DB through the sync->async bridge in
``app.services._hr_persistence``. When the database is unreachable the module
falls back to an in-process, seeded ``_store`` (fail-soft) so the page is still
alive day-one and the app always boots. When the DB is reachable but an org has
no objectives yet, the same seed set is written once so day-one liveness is
preserved *and* persisted.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from app.services import _hr_persistence as _p


@dataclass
class KeyResult:
    id: str
    title: str
    metric_label: str       # "p95 latency", "MRR (USD)", "trainings complete"
    target: float
    current: float
    direction: str = "up"   # up | down (down = lower is better)
    owner: Optional[str] = None
    status: str = "on_track"  # on_track | at_risk | off_track | done

    @property
    def progress_pct(self) -> int:
        if self.target == self.current:
            return 100
        if self.direction == "up":
            if self.target == 0:
                return 100 if self.current >= 0 else 0
            return max(0, min(100, round((self.current / self.target) * 100)))
        # down: closer to (or below) target is good
        baseline = max(self.target * 2, self.current)
        delta = baseline - self.current
        max_delta = baseline - self.target
        if max_delta <= 0:
            return 100
        return max(0, min(100, round((delta / max_delta) * 100)))

    def to_dict(self) -> dict:
        return {**asdict(self), "progress_pct": self.progress_pct}


@dataclass
class Objective:
    id: str
    title: str
    owner: str
    team: Optional[str]
    cycle: str
    status: str = "on_track"
    key_results: list[KeyResult] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def progress_pct(self) -> int:
        if not self.key_results:
            return 0
        return round(sum(kr.progress_pct for kr in self.key_results) / len(self.key_results))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "owner": self.owner,
            "team": self.team,
            "cycle": self.cycle,
            "status": self.status,
            "key_results": [kr.to_dict() for kr in self.key_results],
            "progress_pct": self.progress_pct,
            "created_at": self.created_at,
        }


_lock = threading.RLock()
_store: dict[str, list[Objective]] = {}
_seeded: set[str] = set()
_db_seeded: set[str] = set()  # orgs whose seed rows have been written to the DB


# ---------------------------------------------------------------------------
# Seed data (shared by the in-memory fallback and the one-time DB seed)
# ---------------------------------------------------------------------------
def _seed_rows() -> list[Objective]:
    def _k(**kw) -> KeyResult:
        return KeyResult(id=str(uuid.uuid4()), **kw)

    def _o(**kw) -> Objective:
        return Objective(id=str(uuid.uuid4()), **kw)

    return [
        _o(
            title="Make Foundry the calmest HR OS on the market",
            owner="Casey Reed",
            team="Executive",
            cycle="Q3 2026",
            status="on_track",
            key_results=[
                _k(title="Ship Work OS + Memory + CRM + Finance + Org Graph + Agent Store", metric_label="layers shipped", target=5, current=5, status="done"),
                _k(title="NPS from SMB beta customers >= 60", metric_label="NPS", target=60, current=48, status="at_risk"),
                _k(title="Time-to-value for new SMB <= 30 minutes", metric_label="minutes to first value", target=30, current=45, direction="down", status="at_risk"),
            ],
        ),
        _o(
            title="Cut payments latency by 30%",
            owner="Avery Chen",
            team="Engineering",
            cycle="Q3 2026",
            status="on_track",
            key_results=[
                _k(title="p95 latency <= 220ms", metric_label="ms p95", target=220, current=265, direction="down", status="on_track"),
                _k(title="Zero customer-visible regressions", metric_label="regressions", target=0, current=0, direction="down", status="done"),
            ],
        ),
        _o(
            title="Win 5 mid-market logos",
            owner="Jamie Cole",
            team="Sales",
            cycle="Q3 2026",
            status="at_risk",
            key_results=[
                _k(title="Closed-won logos", metric_label="logos", target=5, current=2, status="at_risk"),
                _k(title="Mid-market pipeline coverage 3.5x", metric_label="x coverage", target=3.5, current=2.4, status="off_track"),
            ],
        ),
        _o(
            title="Q3 review cycle complete with zero rater drift",
            owner="Reese Allen",
            team="HR",
            cycle="Q3 2026",
            status="on_track",
            key_results=[
                _k(title="Self -> manager -> calibration -> approval -> delivery", metric_label="cycle stage", target=6, current=2, status="on_track"),
                _k(title="Bias-flagged feedback < 5%", metric_label="% flagged", target=5, current=3, direction="down", status="on_track"),
            ],
        ),
        _o(
            title="Reach 95% net revenue retention",
            owner="Avery CS Lead",
            team="Customer Success",
            cycle="FY 2026",
            status="on_track",
            key_results=[
                _k(title="NRR", metric_label="% NRR", target=95, current=91, status="on_track"),
                _k(title="Average ticket resolution <= 6 hours", metric_label="hours", target=6, current=7.5, direction="down", status="at_risk"),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# DB row -> dataclass reconstruction
# ---------------------------------------------------------------------------
def _kr_from_row(r: dict) -> KeyResult:
    return KeyResult(
        id=str(r["id"]),
        title=r["title"],
        metric_label=r["metric_label"],
        target=float(r["target"]),
        current=float(r["current"]),
        direction=r["direction"],
        owner=r["owner"],
        status=r["status"],
    )


def _obj_from_row(r: dict, krs: list[KeyResult]) -> Objective:
    created = r["created_at"]
    return Objective(
        id=str(r["id"]),
        title=r["title"],
        owner=r["owner"],
        team=r["team"],
        cycle=r["cycle"],
        status=r["status"],
        key_results=krs,
        created_at=created.isoformat() if hasattr(created, "isoformat") else str(created),
    )


def _db_seed_if_empty(org_id: str) -> None:
    """Write the seed set once for an org that has no objectives yet."""
    if org_id in _db_seeded:
        return

    async def _op(s):
        rows = await _p.afetchall(s, "SELECT count(*) AS n FROM objectives WHERE org_id = CAST(:o AS uuid)", o=org_id)
        if rows and rows[0]["n"]:
            return
        for o in _seed_rows():
            await s.execute(_p.text(
                "INSERT INTO objectives (id, org_id, title, owner, team, cycle, status) "
                "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :title, :owner, :team, :cycle, :status)"),
                {"id": o.id, "org": org_id, "title": o.title, "owner": o.owner,
                 "team": o.team, "cycle": o.cycle, "status": o.status})
            for i, kr in enumerate(o.key_results):
                await s.execute(_p.text(
                    "INSERT INTO key_results (id, objective_id, title, metric_label, target, current, direction, owner, status, position) "
                    "VALUES (CAST(:id AS uuid), CAST(:obj AS uuid), :title, :metric, :target, :current, :direction, :owner, :status, :pos)"),
                    {"id": kr.id, "obj": o.id, "title": kr.title, "metric": kr.metric_label,
                     "target": kr.target, "current": kr.current, "direction": kr.direction,
                     "owner": kr.owner, "status": kr.status, "pos": i})

    _p.tx(_op)
    _db_seeded.add(org_id)


def _db_load(org_id: str) -> list[Objective]:
    _db_seed_if_empty(org_id)
    obj_rows = _p.q(
        "SELECT * FROM objectives WHERE org_id = CAST(:o AS uuid) ORDER BY created_at DESC, id", o=org_id)
    if not obj_rows:
        return []
    kr_rows = _p.q(
        "SELECT kr.* FROM key_results kr JOIN objectives o ON o.id = kr.objective_id "
        "WHERE o.org_id = CAST(:o AS uuid) ORDER BY kr.position, kr.id", o=org_id)
    by_obj: dict[str, list[KeyResult]] = {}
    for r in kr_rows:
        by_obj.setdefault(str(r["objective_id"]), []).append(_kr_from_row(r))
    return [_obj_from_row(r, by_obj.get(str(r["id"]), [])) for r in obj_rows]


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------
def _mem_ensure(org_id: str) -> list[Objective]:
    with _lock:
        if org_id not in _seeded:
            _store[org_id] = _seed_rows()
            _seeded.add(org_id)
        return _store.setdefault(org_id, [])


def _use_db() -> bool:
    return _p.db_available()


# ---------------------------------------------------------------------------
# Public surface (unchanged signatures)
# ---------------------------------------------------------------------------
def list_objectives(org_id: str, *, cycle: Optional[str] = None, team: Optional[str] = None, owner: Optional[str] = None) -> dict:
    if _use_db():
        try:
            rows = _db_load(org_id)
        except Exception as e:
            _p.note_fallback("goals.list_objectives", e)
            rows = _mem_ensure(org_id)
    else:
        rows = _mem_ensure(org_id)

    # Lazy import to avoid circular at module load.
    from app.services.tasks_service import tasks_for_key_result
    out = []
    for o in rows:
        if cycle and o.cycle != cycle:
            continue
        if team and (o.team or "") != team:
            continue
        if owner and o.owner != owner:
            continue
        obj_dict = o.to_dict()
        # Layer linked-task counts onto each KR for the goals page.
        for kr_dict in obj_dict["key_results"]:
            linked = tasks_for_key_result(org_id, kr_dict["id"])
            kr_dict["linked_task_count"] = len(linked)
            kr_dict["linked_task_done"] = sum(1 for t in linked if t.get("status") == "done")
        out.append(obj_dict)

    teams = sorted({o.team for o in rows if o.team})
    cycles = sorted({o.cycle for o in rows})
    on_track = sum(1 for o in rows if o.status == "on_track")
    at_risk = sum(1 for o in rows if o.status == "at_risk")
    off_track = sum(1 for o in rows if o.status == "off_track")
    avg_progress = round(sum(o.progress_pct for o in rows) / len(rows)) if rows else 0
    # WHOSE OBJECTIVES THESE ARE.
    #
    # This service seeds five objectives into an empty tenant — "Win 5
    # mid-market logos" owned by Jamie Cole, across Sales, Engineering,
    # Executive, HR and Customer Success — and the page reported "Objectives 5
    # · On track 4 · At risk 1 · Avg progress 75%" for an organisation with one
    # employee in Operations and none of those teams.
    #
    # Same rule as the recognition feed: an objective owned by somebody who is
    # not in your employee records is a sample objective. It resolves itself
    # the first time a real one is written, with no flag to clear.
    owners = {(o.owner or "").strip().lower() for o in rows if o.owner}
    employees = _employee_names(org_id)
    all_sample = (bool(rows) and employees is not None and bool(owners)
                  and not (owners & employees))
    return {
        "items": out,
        "summary": {
            "total": len(rows),
            "on_track": on_track,
            "at_risk": at_risk,
            "off_track": off_track,
            "avg_progress_pct": avg_progress,
            "cycles": cycles,
            "teams": teams,
        },
        "provenance": {
            "all_sample": all_sample,
            "note": (
                "These objectives were seeded as an example — none of their owners "
                "are in your employee records. Add an objective to start your own."
                if all_sample else None
            ),
        },
    }


def _employee_names(org_id: str) -> Optional[set[str]]:
    """Lower-cased names of this org's employees, or None if unreadable.

    None means "we could not check". Reporting that as "all samples" would put
    a false disclaimer over objectives a team is actually working to.
    """
    try:
        rows = _p.q(
            "SELECT coalesce(preferred_name, legal_name) AS name "
            "FROM public.employees WHERE org_id = CAST(:o AS uuid)", o=org_id)
    except Exception:
        return None
    return {(r["name"] or "").strip().lower() for r in rows if r.get("name")}


def update_key_result(org_id: str, objective_id: str, kr_id: str, payload: dict) -> Optional[dict]:
    if _use_db():
        try:
            return _db_update_key_result(org_id, objective_id, kr_id, payload)
        except Exception as e:
            _p.note_fallback("goals.update_key_result", e)  # fall through to memory
    rows = _mem_ensure(org_id)
    with _lock:
        for o in rows:
            if o.id != objective_id:
                continue
            for kr in o.key_results:
                if kr.id != kr_id:
                    continue
                if "current" in payload:
                    kr.current = float(payload["current"])
                if "status" in payload:
                    kr.status = str(payload["status"])
                return o.to_dict()
    return None


def _db_update_key_result(org_id: str, objective_id: str, kr_id: str, payload: dict) -> Optional[dict]:
    async def _op(s):
        # Confirm the KR belongs to this org's objective.
        chk = await _p.afetchall(s,
            "SELECT kr.id FROM key_results kr JOIN objectives o ON o.id = kr.objective_id "
            "WHERE kr.id = CAST(:kr AS uuid) AND o.id = CAST(:obj AS uuid) AND o.org_id = CAST(:o AS uuid)",
            kr=kr_id, obj=objective_id, o=org_id)
        if not chk:
            return False
        sets, params = [], {"kr": kr_id}
        if "current" in payload:
            sets.append("current = :current")
            params["current"] = float(payload["current"])
        if "status" in payload:
            sets.append("status = :status")
            params["status"] = str(payload["status"])
        if sets:
            await s.execute(_p.text(
                f"UPDATE key_results SET {', '.join(sets)} WHERE id = CAST(:kr AS uuid)"), params)
        return True

    ok = _p.tx(_op)
    if not ok:
        return None
    # Return the refreshed objective.
    for o in _db_load(org_id):
        if o.id == objective_id:
            return o.to_dict()
    return None


def create_objective(org_id: str, payload: dict) -> dict:
    """Create an objective with optional initial key results.

    payload = {
      title, owner, team?, cycle?,
      key_results: [{title, metric_label, target, current?, direction?}, ...]
    }
    """
    krs_payload = payload.get("key_results") or []
    krs: list[KeyResult] = []
    for k in krs_payload:
        try:
            krs.append(KeyResult(
                id=str(uuid.uuid4()),
                title=str(k.get("title") or "Untitled KR"),
                metric_label=str(k.get("metric_label") or "metric"),
                target=float(k.get("target") or 0),
                current=float(k.get("current") or 0),
                direction=str(k.get("direction") or "up"),
                owner=k.get("owner"),
                status=str(k.get("status") or "on_track"),
            ))
        except Exception:
            continue
    o = Objective(
        id=str(uuid.uuid4()),
        title=str(payload.get("title") or "Untitled objective"),
        owner=str(payload.get("owner") or "Org"),
        team=payload.get("team"),
        cycle=str(payload.get("cycle") or "Q3 2026"),
        status=str(payload.get("status") or "on_track"),
        key_results=krs,
    )

    if _use_db():
        try:
            _db_seed_if_empty(org_id)

            async def _op(s):
                await s.execute(_p.text(
                    "INSERT INTO objectives (id, org_id, title, owner, team, cycle, status) "
                    "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :title, :owner, :team, :cycle, :status)"),
                    {"id": o.id, "org": org_id, "title": o.title, "owner": o.owner,
                     "team": o.team, "cycle": o.cycle, "status": o.status})
                for i, kr in enumerate(o.key_results):
                    await s.execute(_p.text(
                        "INSERT INTO key_results (id, objective_id, title, metric_label, target, current, direction, owner, status, position) "
                        "VALUES (CAST(:id AS uuid), CAST(:obj AS uuid), :title, :metric, :target, :current, :direction, :owner, :status, :pos)"),
                        {"id": kr.id, "obj": o.id, "title": kr.title, "metric": kr.metric_label,
                         "target": kr.target, "current": kr.current, "direction": kr.direction,
                         "owner": kr.owner, "status": kr.status, "pos": i})

            _p.tx(_op)
            return o.to_dict()
        except Exception as e:
            _p.note_fallback("goals.create_objective", e)  # fall through to memory
    rows = _mem_ensure(org_id)
    with _lock:
        rows.insert(0, o)
    return o.to_dict()
