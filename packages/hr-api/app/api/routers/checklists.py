"""Onboarding / offboarding checklists (BambooHR-style task lists).

Complements the existing document-centric /onboarding packets: packets collect
compliance items (I-9, W-4, bank details); checklists coordinate the WORK
around a hire/exit — equipment, intros, payroll setup, access removal — with
assignees, due dates and progress.

- GET  /checklists/templates          (auto-seeds two sensible defaults)
- POST /checklists/templates          create custom template (hr)
- POST /checklists/instantiate       create a checklist for an employee (hr)
- GET  /checklists                    all checklists + progress (hr/manager)
- GET  /checklists/me                 caller's checklists (employee self-service)
- GET  /checklists/{id}               detail with tasks
- POST /checklists/tasks/{task_id}/complete | /reopen

Task links deep-link into the rest of the suite (payroll invite flow, AI
interview summaries, documents) so the checklist is the hub, not a silo.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import (
    AuditEvent,
    Checklist,
    ChecklistTask,
    ChecklistTemplate,
    Employee,
)

router = APIRouter(prefix="/checklists", tags=["checklists"])

_HR_ROLES = ("owner", "admin", "hr")
_VIEW_ROLES = ("owner", "admin", "hr", "manager")


def _require(actor: Actor, roles: tuple[str, ...]) -> None:
    if actor.role not in roles:
        raise HTTPException(status_code=403, detail="Not allowed")


# ---------------------------------------------------------------------------
# Default templates. `link` supports {employee_id} substitution at
# instantiate time so tasks deep-link straight into the right flow.
# ---------------------------------------------------------------------------
DEFAULT_ONBOARDING_ITEMS: list[dict] = [
    {"title": "Review AI interview summary & scorecards", "category": "docs",
     "assignee_role": "hr", "due_days_offset": -3, "link": "/app/interviews"},
    {"title": "Send onboarding packet (I-9, W-4, direct deposit)", "category": "docs",
     "assignee_role": "hr", "due_days_offset": -3, "link": "/app/onboarding"},
    {"title": "Set up payroll profile (SSN, bank, withholding) — payroll invite",
     "category": "payroll", "assignee_role": "hr", "due_days_offset": -2,
     "link": "/app/payroll/employees?invite={employee_id}"},
    {"title": "Order laptop & equipment", "category": "equipment",
     "assignee_role": "it", "due_days_offset": -5, "link": None},
    {"title": "Provision email + app accounts", "category": "access",
     "assignee_role": "it", "due_days_offset": -1, "link": None},
    {"title": "Assign time-off policy", "category": "payroll",
     "assignee_role": "hr", "due_days_offset": 0, "link": "/app/pto"},
    {"title": "Manager intro 1:1 scheduled", "category": "intro",
     "assignee_role": "manager", "due_days_offset": 1, "link": None},
    {"title": "Team intro + buddy assigned", "category": "intro",
     "assignee_role": "manager", "due_days_offset": 2, "link": None},
    {"title": "Sign employee handbook", "category": "docs",
     "assignee_role": "employee", "due_days_offset": 3, "link": "/app/documents"},
    {"title": "30-day check-in scheduled", "category": "intro",
     "assignee_role": "manager", "due_days_offset": 30, "link": None},
]

DEFAULT_OFFBOARDING_ITEMS: list[dict] = [
    {"title": "Written notice / termination letter filed", "category": "docs",
     "assignee_role": "hr", "due_days_offset": 0, "link": "/app/documents"},
    {"title": "Knowledge transfer plan agreed", "category": "general",
     "assignee_role": "manager", "due_days_offset": 2, "link": None},
    {"title": "Revoke app + email access", "category": "access",
     "assignee_role": "it", "due_days_offset": 0, "link": None},
    {"title": "Collect laptop, badge & equipment", "category": "equipment",
     "assignee_role": "it", "due_days_offset": 0, "link": None},
    {"title": "Trigger final paycheck (off-cycle run in Payroll; include PTO payout)",
     "category": "payroll", "assignee_role": "hr", "due_days_offset": 0,
     "link": "/app/payroll"},
    {"title": "Exit interview completed", "category": "intro",
     "assignee_role": "hr", "due_days_offset": 1, "link": None},
    {"title": "Benefits / COBRA notice sent", "category": "docs",
     "assignee_role": "hr", "due_days_offset": 3, "link": None},
    {"title": "Records retention check (legal packet export)", "category": "docs",
     "assignee_role": "hr", "due_days_offset": 5, "link": "/app/documents"},
]


async def _ensure_default_templates(db: AsyncSession, org_id: UUID) -> None:
    existing = (await db.execute(select(ChecklistTemplate).where(
        ChecklistTemplate.org_id == org_id))).scalars().all()
    have_kinds = {t.kind for t in existing}
    changed = False
    if "onboarding" not in have_kinds:
        db.add(ChecklistTemplate(org_id=org_id, name="Standard onboarding",
                                 kind="onboarding", items=DEFAULT_ONBOARDING_ITEMS))
        changed = True
    if "offboarding" not in have_kinds:
        db.add(ChecklistTemplate(org_id=org_id, name="Standard offboarding",
                                 kind="offboarding", items=DEFAULT_OFFBOARDING_ITEMS))
        changed = True
    if changed:
        await db.commit()


# =========================================================
# TEMPLATES
# =========================================================
@router.get("/templates")
async def list_templates(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    _require(actor, _VIEW_ROLES)
    org_id = UUID(actor.org_id)
    await _ensure_default_templates(db, org_id)
    rows = (await db.execute(select(ChecklistTemplate).where(
        ChecklistTemplate.org_id == org_id).order_by(ChecklistTemplate.created_at.asc()))).scalars().all()
    return [
        {"id": str(t.id), "name": t.name, "kind": t.kind, "items": t.items or []}
        for t in rows
    ]


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "onboarding"
    items: list[dict] = []


@router.post("/templates")
async def create_template(payload: TemplateCreate, actor: Actor = Depends(require_org),
                          db: AsyncSession = Depends(db_session)):
    _require(actor, _HR_ROLES)
    if payload.kind not in ("onboarding", "offboarding"):
        raise HTTPException(status_code=422, detail="kind must be onboarding or offboarding")
    org_id = UUID(actor.org_id)
    tpl = ChecklistTemplate(org_id=org_id, name=payload.name.strip(),
                            kind=payload.kind, items=payload.items)
    db.add(tpl)
    await db.commit()
    return {"id": str(tpl.id)}


# =========================================================
# INSTANTIATE
# =========================================================
class InstantiateBody(BaseModel):
    employee_id: UUID
    template_id: UUID | None = None
    kind: str = "onboarding"          # used when template_id omitted
    anchor_date: date | None = None   # defaults: start_date (onboarding) / today


@router.post("/instantiate")
async def instantiate(payload: InstantiateBody, actor: Actor = Depends(require_org),
                      db: AsyncSession = Depends(db_session)):
    _require(actor, _HR_ROLES)
    org_id = UUID(actor.org_id)

    emp = (await db.execute(select(Employee).where(
        Employee.id == payload.employee_id, Employee.org_id == org_id))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    await _ensure_default_templates(db, org_id)
    if payload.template_id:
        tpl = (await db.execute(select(ChecklistTemplate).where(
            ChecklistTemplate.id == payload.template_id,
            ChecklistTemplate.org_id == org_id))).scalar_one_or_none()
    else:
        if payload.kind not in ("onboarding", "offboarding"):
            raise HTTPException(status_code=422, detail="kind must be onboarding or offboarding")
        tpl = (await db.execute(select(ChecklistTemplate).where(
            ChecklistTemplate.org_id == org_id,
            ChecklistTemplate.kind == payload.kind,
        ).order_by(ChecklistTemplate.created_at.asc()).limit(1))).scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    anchor = payload.anchor_date or (
        emp.start_date if tpl.kind == "onboarding" and emp.start_date else date.today())

    cl = Checklist(
        org_id=org_id, employee_id=emp.id, template_id=tpl.id, kind=tpl.kind,
        name=f"{tpl.name} — {emp.preferred_name or emp.legal_name}",
        created_by_user_id=UUID(actor.user_id))
    db.add(cl)
    await db.flush()

    for i, item in enumerate(tpl.items or []):
        link = item.get("link")
        if link:
            link = link.replace("{employee_id}", str(emp.id))
        offset = item.get("due_days_offset")
        due = anchor + timedelta(days=int(offset)) if offset is not None else None
        db.add(ChecklistTask(
            org_id=org_id, checklist_id=cl.id,
            title=item.get("title") or f"Task {i + 1}",
            category=item.get("category") or "general",
            assignee_role=item.get("assignee_role") or "hr",
            assignee_employee_id=emp.id if item.get("assignee_role") == "employee" else None,
            due_date=due, link=link, sort_order=i,
        ))

    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type=f"checklist.{tpl.kind}_started", entity_type="checklist", entity_id=cl.id,
        payload={"employee_id": str(emp.id), "template": tpl.name,
                 "anchor_date": anchor.isoformat()},
    ))
    await db.commit()
    return {"id": str(cl.id), "task_count": len(tpl.items or [])}


# =========================================================
# LIST / DETAIL
# =========================================================
def _task_dict(t: ChecklistTask) -> dict:
    return {
        "id": str(t.id), "title": t.title, "category": t.category,
        "assignee_role": t.assignee_role,
        "assignee_employee_id": str(t.assignee_employee_id) if t.assignee_employee_id else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "link": t.link, "status": t.status, "sort_order": t.sort_order,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


async def _checklist_payload(db: AsyncSession, org_id: UUID, checklists: list[Checklist]) -> list[dict]:
    if not checklists:
        return []
    ids = [c.id for c in checklists]
    # org_id is a parameter of this function and was not being used. The ids
    # come from checklists the caller already scoped, so nothing leaked — but
    # an unused tenant parameter beside a query is how the next one does leak.
    tasks = (await db.execute(select(ChecklistTask).where(
        ChecklistTask.checklist_id.in_(ids),
        ChecklistTask.org_id == org_id).order_by(ChecklistTask.sort_order.asc()))).scalars().all()
    by_cl: dict[UUID, list[ChecklistTask]] = {}
    for t in tasks:
        by_cl.setdefault(t.checklist_id, []).append(t)
    emps = {e.id: e for e in (await db.execute(select(Employee).where(
        Employee.org_id == org_id))).scalars().all()}
    out = []
    for c in checklists:
        ts = by_cl.get(c.id, [])
        done = sum(1 for t in ts if t.status == "done")
        emp = emps.get(c.employee_id)
        out.append({
            "id": str(c.id), "kind": c.kind, "name": c.name, "status": c.status,
            "employee_id": str(c.employee_id),
            "employee_name": emp.legal_name if emp else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "progress": {"done": done, "total": len(ts)},
            "tasks": [_task_dict(t) for t in ts],
        })
    return out


@router.get("")
async def list_checklists(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    _require(actor, _VIEW_ROLES)
    org_id = UUID(actor.org_id)
    rows = (await db.execute(select(Checklist).where(
        Checklist.org_id == org_id).order_by(Checklist.created_at.desc()))).scalars().all()
    return await _checklist_payload(db, org_id, rows)


@router.get("/me")
async def my_checklists(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    me = (await db.execute(select(Employee).where(
        Employee.org_id == org_id, Employee.user_id == UUID(actor.user_id)))).scalar_one_or_none()
    if not me:
        return []
    rows = (await db.execute(select(Checklist).where(
        Checklist.org_id == org_id, Checklist.employee_id == me.id,
    ).order_by(Checklist.created_at.desc()))).scalars().all()
    return await _checklist_payload(db, org_id, rows)


@router.get("/{checklist_id}")
async def checklist_detail(checklist_id: UUID, actor: Actor = Depends(require_org),
                           db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    cl = (await db.execute(select(Checklist).where(
        Checklist.id == checklist_id, Checklist.org_id == org_id))).scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Checklist not found")
    if actor.role not in _VIEW_ROLES:
        me = (await db.execute(select(Employee).where(
            Employee.org_id == org_id, Employee.user_id == UUID(actor.user_id)))).scalar_one_or_none()
        if not me or me.id != cl.employee_id:
            raise HTTPException(status_code=403, detail="Not allowed")
    payload = await _checklist_payload(db, org_id, [cl])
    return payload[0]


# =========================================================
# TASK COMPLETION
# =========================================================
async def _get_task_authorized(db: AsyncSession, actor: Actor, task_id: UUID) -> ChecklistTask:
    org_id = UUID(actor.org_id)
    task = (await db.execute(select(ChecklistTask).where(
        ChecklistTask.id == task_id, ChecklistTask.org_id == org_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if actor.role in _VIEW_ROLES:
        return task
    # employees may only touch tasks assigned to them
    me = (await db.execute(select(Employee).where(
        Employee.org_id == org_id, Employee.user_id == UUID(actor.user_id)))).scalar_one_or_none()
    if not me or task.assignee_employee_id != me.id:
        raise HTTPException(status_code=403, detail="Not your task")
    return task


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: UUID, actor: Actor = Depends(require_org),
                        db: AsyncSession = Depends(db_session)):
    from datetime import datetime, timezone
    task = await _get_task_authorized(db, actor, task_id)
    task.status = "done"
    task.completed_by_user_id = UUID(actor.user_id)
    task.completed_at = datetime.now(timezone.utc)

    # auto-complete parent checklist when every task is done
    org_id = UUID(actor.org_id)
    # Scoped explicitly. `task` came from _get_task_authorized, which filters
    # on org_id, so these were already in-tenant by construction — but a reader
    # (and a scanner) should not have to prove that from two functions away.
    siblings = (await db.execute(select(ChecklistTask).where(
        ChecklistTask.checklist_id == task.checklist_id,
        ChecklistTask.org_id == org_id))).scalars().all()
    if all(t.status in ("done", "skipped") or t.id == task.id for t in siblings):
        cl = (await db.execute(select(Checklist).where(
            Checklist.id == task.checklist_id,
            Checklist.org_id == org_id))).scalar_one_or_none()
        if cl:
            cl.status = "completed"

    db.add(AuditEvent(
        org_id=org_id, actor_user_id=UUID(actor.user_id), actor_role=actor.role,
        event_type="checklist.task_completed", entity_type="checklist_task", entity_id=task.id,
        payload={"title": task.title},
    ))
    await db.commit()
    return {"status": "done"}


@router.post("/tasks/{task_id}/reopen")
async def reopen_task(task_id: UUID, actor: Actor = Depends(require_org),
                      db: AsyncSession = Depends(db_session)):
    task = await _get_task_authorized(db, actor, task_id)
    task.status = "open"
    task.completed_by_user_id = None
    task.completed_at = None
    cl = (await db.execute(select(Checklist).where(
        Checklist.id == task.checklist_id,
        Checklist.org_id == UUID(actor.org_id)))).scalar_one_or_none()
    if cl and cl.status == "completed":
        cl.status = "active"
    await db.commit()
    return {"status": "open"}
