"""Employee skills and role skill requirements.

  GET    /skills-management/employees/{id}/skills
  POST   /skills-management/employees/{id}/skills            {skill, level}
  DELETE /skills-management/employees/{id}/skills?skill=...
  GET    /skills-management/roles
  GET    /skills-management/roles/requirements?role=...
  PUT    /skills-management/roles/requirements               {role, items: [{skill, required_level}]}

Who can do what:
  * HR and admins (and managers, for reading) can see and change anyone's skills.
  * An employee can see and change their own.
  * Only HR and admins change what a role requires. Everyone can read it.

The skill and the role travel in the query string or the body, not the path,
because names such as "ci/cd" contain a slash.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services import skills_management_service as svc

router = APIRouter(prefix="/skills-management", tags=["skills-management"])

_MANAGE_ROLES = ("owner", "admin", "hr")
_READ_ROLES = _MANAGE_ROLES + ("manager",)


def _fail(err: svc.SkillsError):
    raise HTTPException(status_code=err.status, detail=err.message)


async def _check_access(db: AsyncSession, actor: Actor, employee_id: str, *, write: bool) -> str:
    """Return who is acting ('hr' or 'self'), or raise. Also checks the employee is in the org."""
    if not await svc.employee_exists(db, actor.org_id, employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    if actor.role in _MANAGE_ROLES:
        return "hr"
    if not write and actor.role in _READ_ROLES:
        return "hr"
    if await svc.employee_id_for_user(db, actor.org_id, actor.user_id) == employee_id:
        return "self"
    raise HTTPException(status_code=403, detail="Not allowed")


@router.get("/employees/{employee_id}/skills")
async def employee_skills(
    employee_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    await _check_access(db, actor, employee_id, write=False)
    return {"employee_id": employee_id, "items": await svc.list_employee_skills(db, actor.org_id, employee_id)}


@router.post("/employees/{employee_id}/skills")
async def save_skill(
    employee_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    source = await _check_access(db, actor, employee_id, write=True)
    try:
        return await svc.save_employee_skill(
            db, actor.org_id, employee_id, payload.get("skill"), payload.get("level"), source,
        )
    except svc.SkillsError as err:
        _fail(err)


@router.delete("/employees/{employee_id}/skills")
async def delete_skill(
    employee_id: str,
    skill: str = Query(...),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    await _check_access(db, actor, employee_id, write=True)
    try:
        removed = await svc.remove_employee_skill(db, actor.org_id, employee_id, skill)
    except svc.SkillsError as err:
        _fail(err)
    if not removed:
        raise HTTPException(status_code=404, detail="That skill is not on this employee")
    return {"removed": True}


@router.get("/roles")
async def roles(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    return {"items": await svc.list_roles(db, actor.org_id)}


@router.get("/roles/requirements")
async def role_requirements(
    role: str = Query(...),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    try:
        return await svc.get_role_requirements(db, actor.org_id, role)
    except svc.SkillsError as err:
        _fail(err)


@router.put("/roles/requirements")
async def save_role_requirements(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in _MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        return await svc.set_role_requirements(db, actor.org_id, payload.get("role"), payload.get("items", []))
    except svc.SkillsError as err:
        _fail(err)
