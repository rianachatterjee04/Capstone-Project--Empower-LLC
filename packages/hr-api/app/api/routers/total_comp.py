"""Total Compensation Unification API.

One Total-Comp view per employee that aggregates EVERY pay stream from its real
source (HR cash + benefits, packages/api commission, packages/payroll actuals,
HR cap-table equity) with a target-vs-actual breakdown.

Endpoints (mounted under /api by the aggregate router):
  GET /comp/total/me?plan_year=              the caller's own total comp (any employee)
  GET /comp/total/{employee_id}?plan_year=   single employee (HR/admin, or self)
  GET /comp/total?plan_year=&employee_ids=   roster / team roll-up (HR/admin)

Every source is fail-soft: a component that cannot be fetched is flagged
`available=false` with a reason and contributes zero — the endpoint never 500s
because a downstream is down.  The caller's bearer token is forwarded to the
commission API (which is user-authenticated); the payroll seam uses the shared
X-Internal-Secret.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.total_comp_service import build_total_comp

router = APIRouter(prefix="/comp", tags=["total-comp"])

ADMIN_ROLES = ("owner", "admin", "hr", "manager")


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def _resolve_self_employee_id(db: AsyncSession, actor: Actor) -> Optional[str]:
    """Find the employee row belonging to the caller.

    The `(:email)::text` cast is load-bearing. This predicate used to read
    `(:email IS NOT NULL AND email = :email)`, and on asyncpg a bare parameter
    compared only against NULL has no inferable type, so Postgres refused the
    statement with AmbiguousParameterError -- every self-service lookup 500'd.
    The NULL guard was redundant anyway: `email = NULL` is NULL, which already
    fails to match, so dropping it changes no behaviour and lets the column
    supply the type.
    """
    email = actor.claims.get("email")
    row = (await db.execute(text("""
        SELECT id FROM public.employees
        WHERE org_id = :org AND (user_id = :uid OR email = (:email)::text)
        LIMIT 1
    """), {"org": actor.org_id, "uid": actor.user_id, "email": email})).first()
    return str(row[0]) if row else None


@router.get("/total/me")
async def my_total_comp(
    plan_year: int = Query(default_factory=lambda: date.today().year),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    authorization: Optional[str] = Header(default=None),
):
    """The caller's OWN total comp -- the employee self-service surface.

    WHY THIS EXISTS
    The employee portal has no way to know its own employee id, so it called
    `GET /comp/total` (no id) to mean "mine". That path is the roster roll-up,
    which is HR/admin-only, so every employee saw "Roster total comp is
    HR/admin/manager only" on their own compensation page. The employee was not
    being denied their own data -- they were asking the wrong question.

    Declared BEFORE /total/{employee_id} on purpose: FastAPI matches in
    declaration order, and the parameterised route would otherwise swallow
    "me" and look up an employee whose id is literally "me".
    """
    my_id = await _resolve_self_employee_id(db, actor)
    if not my_id:
        raise HTTPException(
            status_code=404,
            detail="No employee record is linked to your account, so your "
                   "compensation cannot be assembled.",
        )
    return await build_total_comp(
        db, org_id=actor.org_id, employee_id=my_id, plan_year=plan_year,
        bearer_token=_bearer(authorization),
    )


@router.get("/total/{employee_id}")
async def employee_total_comp(
    employee_id: str,
    plan_year: int = Query(default_factory=lambda: date.today().year),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    authorization: Optional[str] = Header(default=None),
):
    """Full total comp for ONE employee.

    HR/admin/manager can view anyone in their org; an employee may view only
    their own record (resolved from their token)."""
    if actor.role not in ADMIN_ROLES:
        my_id = await _resolve_self_employee_id(db, actor)
        if my_id != employee_id:
            raise HTTPException(status_code=403,
                                detail="You can only view your own total compensation")
    return await build_total_comp(
        db, org_id=actor.org_id, employee_id=employee_id, plan_year=plan_year,
        bearer_token=_bearer(authorization),
    )


@router.get("/total")
async def roster_total_comp(
    plan_year: int = Query(default_factory=lambda: date.today().year),
    employee_ids: Optional[str] = Query(
        default=None, description="comma-separated employee ids; defaults to the org roster"),
    limit: int = Query(default=100, le=500),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    authorization: Optional[str] = Header(default=None),
):
    """Team / roster roll-up: total comp for many employees plus an org total.

    HR/admin/manager only.  Returns per-employee payloads and an aggregate of
    target vs actual across the roster."""
    if actor.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403,
                            detail="Roster total comp is HR/admin/manager only")

    if employee_ids:
        ids = [e.strip() for e in employee_ids.split(",") if e.strip()][:limit]
    else:
        rows = (await db.execute(text("""
            SELECT id FROM public.employees
            WHERE org_id = :org AND status NOT IN ('terminated', 'offboarded')
            ORDER BY legal_name LIMIT :lim
        """), {"org": actor.org_id, "lim": limit})).all()
        ids = [str(r[0]) for r in rows]

    token = _bearer(authorization)
    people = []
    roll_target = roll_actual = 0.0
    for eid in ids:
        tc = await build_total_comp(
            db, org_id=actor.org_id, employee_id=eid, plan_year=plan_year,
            bearer_token=token,
        )
        people.append(tc)
        roll_target += tc["totals"]["target_total_comp"]
        roll_actual += tc["totals"]["actual_total_comp"]

    return {
        "plan_year": plan_year,
        "count": len(people),
        "roll_up": {
            "target_total_comp": round(roll_target, 2),
            "actual_total_comp": round(roll_actual, 2),
            "variance_to_target": round(roll_actual - roll_target, 2),
        },
        "employees": people,
    }
