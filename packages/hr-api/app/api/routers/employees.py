from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.core.json_utils import json_safe
from uuid import UUID
from datetime import date

from app.api.deps import require_org, db_session, Actor
from app.api.schemas import EmployeeOut, EmployeeCreate
from app.db.models import AuditEvent, Employee
# ⭐ Behavioral OS
from app.workflow.engine import engine


router = APIRouter(prefix="/employees", tags=["employees"])


# =========================================================
# LIST
# =========================================================
@router.get("", response_model=list[EmployeeOut])
async def list_employees(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    org_id = UUID(actor.org_id)
    q = select(Employee).where(Employee.org_id == org_id).order_by(Employee.created_at.asc())
    res = await db.execute(q)
    return res.scalars().all()


# =========================================================
# CREATE (Offer accepted -> employee record created)
# =========================================================
@router.post("", response_model=EmployeeOut)
async def create_employee(payload: EmployeeCreate, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)

    # EmployeeCreate.status has a default ("invited"), so model_dump() always
    # includes `status`. Passing status="pending_onboarding" as an explicit
    # kwarg too raised "TypeError: multiple values for keyword argument
    # 'status'" on every call. Override status in the dump so a newly-created
    # (offer-accepted) employee is pending_onboarding, exactly as before.
    data = payload.model_dump()
    data["status"] = "pending_onboarding"

    emp = Employee(
        org_id=org_id,
        **data
    )

    db.add(emp)
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="employee.created",
        entity_type="employee",
        entity_id=emp.id,
        payload=json_safe(payload.model_dump())
    ))

    await db.commit()
    await db.refresh(emp)

    # 🧠 BRAIN TRIGGER
    engine.trigger(
        "employee.created",
        {"employee_id": str(emp.id)}
    )

    # 🧠 Company Brain — publish the hire into the shared knowledge graph (fail-open).
    try:
        from app.brain_client import record_hire
        record_hire(str(org_id), employee_id=str(emp.id),
                    name=getattr(emp, "legal_name", "") or getattr(payload, "legal_name", ""),
                    department=getattr(payload, "department", "") or "",
                    manager_id=str(getattr(payload, "manager_employee_id", "") or ""))
    except Exception:
        pass

    return emp


# =========================================================
# ACTIVATE (after onboarding complete)
# =========================================================
@router.post("/{employee_id}/activate")
async def activate_employee(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    emp = await db.get(Employee, UUID(employee_id))
    if not emp or str(emp.org_id) != actor.org_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    emp.status = "active"
    emp.start_date = emp.start_date or date.today()

    db.add(AuditEvent(
        org_id=emp.org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="employee.activated",
        entity_type="employee",
        entity_id=emp.id,
        payload={}
    ))

    await db.commit()

    # 🧠 workflow: provisioning + payroll eligibility
    engine.trigger(
        "employee.activated",
        {"employee_id": str(emp.id)}
    )

    return {"status": "active"}


# =========================================================
# ASSIGN MANAGER (org graph)
# =========================================================
@router.post("/{employee_id}/manager/{manager_id}")
async def assign_manager(employee_id: str, manager_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    _updated = await db.execute(text("""
        update public.employees
        set manager_employee_id=:manager
        where id=:emp and org_id=:org
    """), {"manager": manager_id, "emp": employee_id, "org": actor.org_id})
    if _updated.rowcount == 0:
        # The WHERE clause is org-scoped, so zero rows means the id does not
        # belong to this organisation (or does not exist). Continuing wrote an
        # audit event recording an action that never happened, and answered the
        # caller as though it had.
        raise HTTPException(status_code=404, detail="no such employee in this organisation")


    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="employee.manager_changed",
        entity_type="employee",
        entity_id=UUID(employee_id),
        payload={"manager_id": manager_id}
    ))

    await db.commit()

    engine.trigger(
        "employee.manager.assigned",
        {"employee_id": employee_id, "manager_id": manager_id}
    )

    return {"manager_id": manager_id}


# =========================================================
# TERMINATE
# =========================================================
@router.post("/{employee_id}/terminate")
async def terminate(employee_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    reason = payload.get("reason","unspecified")

    _updated = await db.execute(text("""
        update public.employees
        set status='terminated',
            termination_date=current_date,
            termination_reason=:reason
        where id=:id and org_id=:org
    """), {"id": employee_id, "org": actor.org_id, "reason": reason})
    if _updated.rowcount == 0:
        # The WHERE clause is org-scoped, so zero rows means the id does not
        # belong to this organisation (or does not exist). Continuing wrote an
        # audit event recording an action that never happened, and answered the
        # caller as though it had.
        raise HTTPException(status_code=404, detail="no such employee in this organisation")


    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="employee.terminated",
        entity_type="employee",
        entity_id=UUID(employee_id),
        payload={"reason": reason}
    ))

    await db.commit()

    engine.trigger(
        "employee.terminated",
        {"employee_id": employee_id, "reason": reason}
    )

    return {"status":"terminated"}


# =========================================================
# REHIRE
# =========================================================
@router.post("/{employee_id}/rehire")
async def rehire(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    _updated = await db.execute(text("""
        update public.employees
        set status='active',
            termination_date=null,
            termination_reason=null
        where id=:id and org_id=:org
    """), {"id": employee_id, "org": actor.org_id})
    if _updated.rowcount == 0:
        # The WHERE clause is org-scoped, so zero rows means the id does not
        # belong to this organisation (or does not exist). Continuing wrote an
        # audit event recording an action that never happened, and answered the
        # caller as though it had.
        raise HTTPException(status_code=404, detail="no such employee in this organisation")


    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="employee.rehired",
        entity_type="employee",
        entity_id=UUID(employee_id),
        payload={}
    ))

    await db.commit()

    engine.trigger(
        "employee.rehired",
        {"employee_id": employee_id}
    )

    return {"status":"active"}


# =========================================================
# ORG TREE
# =========================================================
@router.get("/org-tree")
async def org_tree(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    rows = (await db.execute(text("""
        select id, manager_employee_id, legal_name
        from public.employees
        where org_id=:org
    """), {"org": actor.org_id})).fetchall()

    return [
        {"id": str(r[0]), "manager_id": str(r[1]) if r[1] else None, "name": r[2]}
        for r in rows
    ]