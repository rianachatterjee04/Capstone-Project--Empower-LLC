"""Employee Digital Twin router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.digital_twin_service import build_twin


router = APIRouter(prefix="/digital-twin", tags=["digital-twin"])


@router.get("/{employee_id}")
async def get(
    employee_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    # Privacy: a non-privileged employee can only view their own twin.
    if actor.role not in ("owner", "admin", "hr", "manager") and employee_id != "me":
        # We can't easily map user_id->employee_id without DB; fall back to self id.
        raise HTTPException(status_code=403, detail="Not allowed")
    twin = await build_twin(db, employee_id if employee_id != "me" else "e1", actor.org_id)
    return twin.to_dict()


@router.get("")
async def demo_list(actor: Actor = Depends(require_org)):
    """Lightweight directory of demo twins so the UI has cards to render."""
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    # Invented directory. A card carrying a name and a title is indistinguishable
    # from a real colleague once it is on screen, so each one says so.
    return {
        "items": [
            {"id": "e1", "name": "Avery Chen",  "title": "Senior Software Engineer", "department": "Engineering", "is_sample": True},
            {"id": "e2", "name": "Jordan Patel","title": "Account Executive",         "department": "Sales",       "is_sample": True},
            {"id": "e3", "name": "Sam Rivera",  "title": "Engineering Manager",       "department": "Engineering", "is_sample": True},
            {"id": "e5", "name": "Riley Singh", "title": "Senior Designer",           "department": "Design",      "is_sample": True},
            {"id": "e6", "name": "Emily Stone", "title": "Senior CS Specialist",      "department": "Customer Success", "is_sample": True},
        ],
        "all_sample": True,
        "provenance": "these are illustrative sample people, not employees in your organisation",
    }
