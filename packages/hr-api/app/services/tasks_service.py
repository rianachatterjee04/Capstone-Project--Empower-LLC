"""Workforce execution layer.

This is the substrate that turns Foundry People into an operating system:
every workflow (onboarding, review cycle, comp cycle, compliance, learning)
emits tasks that show up in the user's inbox + the team workspace.

The store is in-process for the demo — it carries enough fidelity (owner,
project, due date, source) that the UI feels real, and the auto-orchestration
rules ship as data so a real DB-backed implementation can replace the store
without touching callers.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
@dataclass
class Task:
    id: str
    org_id: str
    title: str
    description: str = ""
    status: str = "todo"               # todo | doing | blocked | done
    priority: str = "normal"           # low | normal | high | urgent
    # True for the seeded demo tasks, which name invented people as both
    # owner and subject.
    is_sample: bool = False
    source: str = "manual"             # onboarding | offboarding | performance | comp | compliance | learning | manual
    project: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    owner_role: Optional[str] = None
    assigned_by_id: Optional[str] = None
    assigned_by_name: Optional[str] = None
    department: Optional[str] = None
    related_employee_id: Optional[str] = None
    related_employee_name: Optional[str] = None
    due_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ai_generated: bool = False
    ai_rationale: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    objective_id: Optional[str] = None
    key_result_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
_lock = threading.RLock()
_store: dict[str, list[Task]] = {}
_seeded_orgs: set[str] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _seed_demo(org_id: str) -> None:
    """Synthetic but coherent task set so demos look alive."""
    now = _now()

    def _t(**kwargs) -> Task:
        # Every seeded task below names invented people -- as the task's owner,
        # and as the employee it concerns. "Approve Avery Chen Q2 self review"
        # in someone's queue is indistinguishable from real work until it is
        # marked.
        return Task(
            id=str(uuid.uuid4()),
            org_id=org_id,
            is_sample=True,
            **kwargs,
        )

    rows: list[Task] = [
        _t(
            title="Approve Avery Chen Q2 self review",
            description="Self review submitted. Manager review next.",
            source="performance",
            project="Q2 review cycle",
            priority="high",
            owner_name="Sam Rivera",
            owner_role="manager",
            related_employee_id="e1",
            related_employee_name="Avery Chen",
            department="Engineering",
            due_at=_iso(now + timedelta(days=2)),
            ai_generated=True,
            ai_rationale="Aging review — self stage completed > 5 days ago.",
            tags=["review", "manager-action"],
        ),
        _t(
            title="Schedule onboarding equipment pickup",
            description="Riley Singh starts in 6 days. Confirm laptop + peripherals shipped.",
            source="onboarding",
            project="Riley Singh onboarding",
            priority="high",
            owner_name="IT Ops",
            owner_role="hr",
            related_employee_name="Riley Singh",
            department="Design",
            due_at=_iso(now + timedelta(days=1)),
            ai_generated=True,
            ai_rationale="Onboarding D-6: equipment step is overdue per the canonical journey.",
            tags=["onboarding", "it"],
        ),
        _t(
            title="Send buddy intro for new hire",
            description="Assign a buddy and schedule a 30-min coffee in week 1.",
            source="onboarding",
            project="Riley Singh onboarding",
            priority="normal",
            owner_name="Riley's Manager",
            owner_role="manager",
            related_employee_name="Riley Singh",
            department="Design",
            due_at=_iso(now + timedelta(days=4)),
            ai_generated=True,
            ai_rationale="Buddy assignment slot reached.",
            tags=["onboarding", "manager-action"],
        ),
        _t(
            title="Review Jordan Patel attrition risk",
            description="Compa-ratio drift + 22 mo without raise. Comp + 1:1 recommended.",
            source="performance",
            project="Retention",
            priority="urgent",
            owner_name="HR Business Partner",
            owner_role="hr",
            related_employee_id="e2",
            related_employee_name="Jordan Patel",
            department="Sales",
            due_at=_iso(now + timedelta(days=2)),
            ai_generated=True,
            ai_rationale="Workforce risk engine flagged 'high' band for this employee.",
            tags=["retention", "comp"],
        ),
        _t(
            title="Finalise Q2 calibration packet",
            description="Cross-team rater drift review. HR + leadership.",
            source="performance",
            project="Q2 review cycle",
            priority="high",
            owner_name="People Ops",
            owner_role="hr",
            due_at=_iso(now + timedelta(days=5)),
            tags=["review", "calibration"],
        ),
        _t(
            title="Close out 2 high-severity ombudsman cases",
            description="Both have been open > 30 days. Reporter updates due this week.",
            source="compliance",
            project="Compliance",
            priority="urgent",
            owner_name="Legal + HR",
            owner_role="hr",
            due_at=_iso(now + timedelta(days=3)),
            tags=["compliance", "case"],
        ),
        _t(
            title="Update security training (SOC 2 annual)",
            description="3 employees overdue. Send reminders + escalate week 2.",
            source="compliance",
            project="Compliance",
            priority="high",
            owner_name="People Ops",
            owner_role="hr",
            due_at=_iso(now + timedelta(days=4)),
            tags=["learning", "compliance"],
            ai_generated=True,
            ai_rationale="Compliance agent flagged 3 employees with stale training.",
        ),
        _t(
            title="Run workforce planning agent for Q3",
            description="Forecast hiring impact on payroll. CS likely understaffed in 45d.",
            source="manual",
            project="Workforce planning",
            priority="normal",
            owner_name="HR",
            owner_role="hr",
            due_at=_iso(now + timedelta(days=10)),
            ai_generated=True,
            ai_rationale="No workforce planning run logged this quarter.",
            tags=["planning"],
        ),
        _t(
            title="Approve 4 PTO requests",
            description="3 routine + 1 overlapping with on-call rotation.",
            source="manual",
            project="People ops",
            priority="normal",
            owner_name="Managers",
            owner_role="manager",
            due_at=_iso(now + timedelta(days=1)),
            tags=["pto", "approval"],
        ),
        _t(
            title="Manager 1:1 — Avery Chen",
            description="Suggested weekly recurrence. Push agenda to docs.",
            source="manual",
            project="People ops",
            priority="normal",
            owner_name="Sam Rivera",
            owner_role="manager",
            related_employee_id="e1",
            related_employee_name="Avery Chen",
            department="Engineering",
            due_at=_iso(now + timedelta(days=2)),
            tags=["1on1", "manager-action"],
        ),
        _t(
            title="Recognize Emily Stone",
            description="Customer-saving incident response last week. Public recognition + bonus pulse.",
            source="manual",
            project="Recognition",
            priority="normal",
            owner_name="VP People",
            owner_role="manager",
            related_employee_name="Emily Stone",
            department="Customer Success",
            due_at=_iso(now + timedelta(days=2)),
            ai_generated=True,
            ai_rationale="Recognition agent detected high-impact incident.",
            tags=["recognition"],
        ),
        _t(
            title="Complete W-4 form",
            description="Employee task as part of onboarding packet.",
            source="onboarding",
            project="Avery Chen onboarding",
            status="done",
            priority="normal",
            owner_name="Avery Chen",
            owner_role="employee",
            related_employee_name="Avery Chen",
            department="Engineering",
            due_at=_iso(now - timedelta(days=2)),
            tags=["onboarding", "employee-action"],
        ),
        _t(
            title="Comp letter for Sam Rivera",
            description="Annual merit cycle. Pending finance approval.",
            source="comp",
            project="Q2 comp cycle",
            priority="high",
            owner_name="Finance",
            owner_role="hr",
            related_employee_name="Sam Rivera",
            department="Engineering",
            due_at=_iso(now + timedelta(days=6)),
            tags=["comp", "approval"],
        ),
        _t(
            title="Refresh skills inventory — Design team",
            description="Skills graph is stale; 2 designers added new tools recently.",
            source="learning",
            project="Skills graph",
            priority="low",
            owner_name="HR + Manager",
            owner_role="hr",
            department="Design",
            due_at=_iso(now + timedelta(days=8)),
            tags=["learning", "skills"],
        ),
    ]

    _store[org_id] = rows


def _ensure(org_id: str) -> list[Task]:
    with _lock:
        if org_id not in _seeded_orgs:
            _seed_demo(org_id)
            _seeded_orgs.add(org_id)
        return _store.setdefault(org_id, [])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def list_tasks(
    org_id: str,
    *,
    status: Optional[str] = None,
    owner_role: Optional[str] = None,
    source: Optional[str] = None,
    department: Optional[str] = None,
    project: Optional[str] = None,
    employee_id: Optional[str] = None,
    owner_name: Optional[str] = None,
) -> list[dict]:
    rows = _ensure(org_id)
    def keep(t: Task) -> bool:
        if status and t.status != status: return False
        if owner_role and t.owner_role != owner_role: return False
        if source and t.source != source: return False
        if department and (t.department or "") != department: return False
        if project and (t.project or "") != project: return False
        if employee_id and t.related_employee_id != employee_id: return False
        if owner_name and (t.owner_name or "").lower() != owner_name.lower(): return False
        return True
    filtered = [t for t in rows if keep(t)]
    filtered.sort(key=lambda t: (t.status == "done", t.due_at or ""))
    return [t.to_dict() for t in filtered]


def create_task(org_id: str, payload: dict) -> dict:
    rows = _ensure(org_id)
    t = Task(
        id=str(uuid.uuid4()),
        org_id=org_id,
        title=str(payload.get("title") or "Untitled task"),
        description=str(payload.get("description") or ""),
        status=str(payload.get("status") or "todo"),
        priority=str(payload.get("priority") or "normal"),
        source=str(payload.get("source") or "manual"),
        project=payload.get("project"),
        owner_id=payload.get("owner_id"),
        owner_name=payload.get("owner_name"),
        owner_role=payload.get("owner_role"),
        assigned_by_id=payload.get("assigned_by_id"),
        assigned_by_name=payload.get("assigned_by_name"),
        department=payload.get("department"),
        related_employee_id=payload.get("related_employee_id"),
        related_employee_name=payload.get("related_employee_name"),
        due_at=payload.get("due_at"),
        ai_generated=bool(payload.get("ai_generated") or False),
        ai_rationale=payload.get("ai_rationale"),
        tags=list(payload.get("tags") or []),
        objective_id=payload.get("objective_id"),
        key_result_id=payload.get("key_result_id"),
    )
    with _lock:
        rows.insert(0, t)
    return t.to_dict()


def tasks_for_key_result(org_id: str, kr_id: str) -> list[dict]:
    rows = _ensure(org_id)
    return [t.to_dict() for t in rows if t.key_result_id == kr_id]


def link_task_to_kr(org_id: str, task_id: str, objective_id: Optional[str], kr_id: Optional[str]) -> Optional[dict]:
    rows = _ensure(org_id)
    with _lock:
        for t in rows:
            if t.id == task_id:
                t.objective_id = objective_id
                t.key_result_id = kr_id
                t.updated_at = _iso(_now())
                return t.to_dict()
    return None


def update_task(org_id: str, task_id: str, payload: dict) -> Optional[dict]:
    rows = _ensure(org_id)
    with _lock:
        for t in rows:
            if t.id == task_id:
                for k, v in payload.items():
                    if hasattr(t, k):
                        setattr(t, k, v)
                t.updated_at = _iso(_now())
                return t.to_dict()
    return None


def projects_overview(org_id: str) -> list[dict]:
    rows = _ensure(org_id)
    by_project: dict[str, dict] = {}
    for t in rows:
        key = t.project or "Unassigned"
        bucket = by_project.setdefault(key, {
            "project": key,
            "total": 0,
            "todo": 0,
            "doing": 0,
            "blocked": 0,
            "done": 0,
            "owner_roles": set(),
            "departments": set(),
            "sources": set(),
        })
        bucket["total"] += 1
        bucket[t.status] = bucket.get(t.status, 0) + 1
        if t.owner_role: bucket["owner_roles"].add(t.owner_role)
        if t.department: bucket["departments"].add(t.department)
        bucket["sources"].add(t.source)
    out = []
    for k, b in by_project.items():
        completion = 0
        if b["total"]:
            completion = round((b.get("done", 0) / b["total"]) * 100)
        out.append({
            "project": b["project"],
            "total": b["total"],
            "todo": b.get("todo", 0),
            "doing": b.get("doing", 0),
            "blocked": b.get("blocked", 0),
            "done": b.get("done", 0),
            "completion_percent": completion,
            "owner_roles": sorted(b["owner_roles"]),
            "departments": sorted(b["departments"]),
            "sources": sorted(b["sources"]),
        })
    out.sort(key=lambda r: r["completion_percent"])
    return out


def tasks_summary(org_id: str) -> dict:
    rows = _ensure(org_id)
    total = len(rows)
    open_ = sum(1 for t in rows if t.status not in ("done",))
    urgent = sum(1 for t in rows if t.priority == "urgent" and t.status != "done")
    ai = sum(1 for t in rows if t.ai_generated and t.status != "done")
    overdue = 0
    now = _now()
    for t in rows:
        if t.status == "done" or not t.due_at:
            continue
        try:
            d = datetime.fromisoformat(t.due_at)
            if d < now:
                overdue += 1
        except Exception:
            pass
    return {
        "total": total,
        "open": open_,
        "urgent": urgent,
        "ai_generated_open": ai,
        "overdue": overdue,
    }


# ---------------------------------------------------------------------------
# Auto-orchestration — public seam used by other services / agents.
# ---------------------------------------------------------------------------
def orchestrate_onboarding(org_id: str, employee_name: str, role: str, manager_name: str = "Manager") -> list[dict]:
    """Generate the canonical onboarding task set for a new hire."""
    now = _now()
    tasks = [
        ("Send offer for e-signature",    "hr", "HR", -7),
        ("Collect I-9 + W-4",              "hr", "HR", -5),
        ("Order equipment",                "hr", "IT", -3),
        ("Assign workspace + accounts",    "hr", "IT", -1),
        ("Schedule Day-1 1:1",             "manager", manager_name, 0),
        ("Assign buddy",                   "manager", manager_name, 1),
        ("Complete security training",     "employee", employee_name, 7),
        ("Stakeholder map",                "manager", manager_name, 14),
        (f"Complete {role} learning path", "employee", employee_name, 30),
        ("First formal check-in (30d)",    "manager", manager_name, 30),
        ("90-day performance review",      "manager", manager_name, 90),
    ]
    out = []
    for title, role_, owner, day in tasks:
        out.append(create_task(org_id, {
            "title": title,
            "source": "onboarding",
            "project": f"{employee_name} onboarding",
            "owner_role": role_,
            "owner_name": owner,
            "related_employee_name": employee_name,
            "priority": "high" if day <= 1 else "normal",
            "due_at": _iso(now + timedelta(days=day)),
            "ai_generated": True,
            "ai_rationale": "Auto-orchestrated from the canonical onboarding journey.",
            "tags": ["onboarding"],
        }))
    return out


def orchestrate_review_cycle(org_id: str, cycle_name: str = "Q2 review cycle") -> list[dict]:
    """Generate the canonical review cycle setup tasks."""
    now = _now()
    rows = [
        ("Open self review form for the company",  "hr", "HR", 0),
        ("Nominate peer reviewers",                  "employee", "Each employee", 3),
        ("Manager reviews due",                      "manager", "Each manager", 14),
        ("Calibration session",                      "hr", "HR + leadership", 18),
        ("Final approvals",                          "hr", "HR", 21),
        ("Deliver reviews to employees",             "manager", "Each manager", 24),
    ]
    out = []
    for title, role_, owner, day in rows:
        out.append(create_task(org_id, {
            "title": title,
            "source": "performance",
            "project": cycle_name,
            "owner_role": role_,
            "owner_name": owner,
            "priority": "high" if day <= 3 else "normal",
            "due_at": _iso(now + timedelta(days=day)),
            "ai_generated": True,
            "ai_rationale": "Auto-orchestrated from the canonical review cycle.",
            "tags": ["review", "cycle"],
        }))
    return out
