"""Internal talent marketplace router."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org, required_field
from app.services.learning_service import extract_skills_from_text, required_skills_for
from app.services.talent_marketplace_service import (
    OpenInternalRole,
    list_internal_roles,
    match_employee_to_marketplace,
    succession_candidates_for_role,
)


router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def _tenure_years(start_date) -> float:
    if not start_date:
        return 1.0
    try:
        if hasattr(start_date, "year"):
            d = start_date
            now = datetime.utcnow().date()
            return max(0.1, (now - d).days / 365.25)
        d = datetime.fromisoformat(str(start_date)).date()
        return max(0.1, (datetime.utcnow().date() - d).days / 365.25)
    except Exception:
        return 1.0


async def _roles_from_jobs(db: AsyncSession, org_id: str) -> list[OpenInternalRole]:
    """Open/published/active job postings as internal mobility roles."""
    rows = (await db.execute(text("""
        select id, title, description, location, status
          from public.job_postings
         where org_id = cast(:org_id as uuid)
           and lower(status) in ('open', 'published', 'active')
         order by created_at desc
    """), {"org_id": org_id})).mappings().all()
    roles: list[OpenInternalRole] = []
    for r in rows:
        skills = extract_skills_from_text(r["description"] or "") or required_skills_for(r["title"] or "")
        title = r["title"] or "Open role"
        seniority = "senior" if any(w in title.lower() for w in ("senior", "lead", "principal", "staff", "director", "vp")) else "mid"
        roles.append(OpenInternalRole(
            id=str(r["id"]),
            title=title,
            department=r["location"] or "Internal",
            skills_required=skills[:8] or ["communication"],
            seniority=seniority,
            posted_by="job_postings",
        ))
    return roles


async def _employee_pool(db: AsyncSession, org_id: str) -> list[dict]:
    """Active employees shaped for marketplace matching (real org data)."""
    from app.services.calibration_service import succession_pool
    pool = succession_pool(org_id) or []
    if pool:
        return pool

    rows = (await db.execute(text("""
        select e.id, e.legal_name, e.job_title, e.start_date,
               (select pr.rating
                  from public.performance_reviews pr
                 where pr.org_id = e.org_id and pr.employee_id = e.id
                   and pr.rating is not null
                 order by pr.created_at desc
                 limit 1) as rating
          from public.employees e
         where e.org_id = cast(:org_id as uuid)
           and e.status = 'active'
         order by e.legal_name
    """), {"org_id": org_id})).mappings().all()

    out: list[dict] = []
    for r in rows:
        title = r["job_title"] or ""
        skills = required_skills_for(title) if title else []
        out.append({
            "id": str(r["id"]),
            "name": r["legal_name"],
            "skills": skills,
            "performance_rating": float(r["rating"]) if r["rating"] is not None else 3.5,
            "tenure_years": _tenure_years(r["start_date"]),
        })
    return out


@router.get("/roles")
async def roles(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    real = await _roles_from_jobs(db, actor.org_id)
    if real:
        return {"items": [r.to_dict() for r in real]}
    # No open reqs yet — keep matcher usable with the static internal-role taxonomy.
    return {"items": list_internal_roles()}


@router.post("/match-employee")
async def match_employee(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if not payload.get("employee_id") or not payload.get("employee_name"):
        raise HTTPException(status_code=400, detail="employee_id and employee_name required")
    role_rows = await _roles_from_jobs(db, actor.org_id)
    if role_rows:
        from app.services.talent_marketplace_service import match_employee_to_role
        matches = [
            match_employee_to_role(
                employee_id=str(required_field(payload, "employee_id")),
                employee_name=str(required_field(payload, "employee_name")),
                employee_skills=payload.get("skills") or [],
                role=role,
                performance_rating=float(payload.get("performance_rating") or 3.5),
                tenure_years=float(payload.get("tenure_years") or 1.0),
            )
            for role in role_rows
        ]
        matches.sort(key=lambda m: m.score, reverse=True)
        return {"items": [m.to_dict() for m in matches]}
    matches = match_employee_to_marketplace(
        employee_id=str(required_field(payload, "employee_id")),
        employee_name=str(required_field(payload, "employee_name")),
        employee_skills=payload.get("skills") or [],
        performance_rating=float(payload.get("performance_rating") or 3.5),
        tenure_years=float(payload.get("tenure_years") or 1.0),
    )
    return {"items": [m.to_dict() for m in matches]}


@router.get("/succession/{role_id}")
async def succession(role_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    # Real succession pool = high-performance / high-potential placements, else
    # all active employees. Role may be a job_posting id or a demo role id.
    pool = await _employee_pool(db, actor.org_id)
    real_roles = await _roles_from_jobs(db, actor.org_id)
    role = next((r for r in real_roles if r.id == role_id), None)
    if role is not None:
        from app.services.talent_marketplace_service import match_employee_to_role
        matches = [
            match_employee_to_role(
                employee_id=str(e["id"]),
                employee_name=e["name"],
                employee_skills=e.get("skills") or [],
                role=role,
                performance_rating=float(e.get("performance_rating") or 3.5),
                tenure_years=float(e.get("tenure_years") or 1.0),
            )
            for e in pool
        ]
        matches.sort(key=lambda m: m.score, reverse=True)
        return {"items": [m.to_dict() for m in matches]}
    matches = succession_candidates_for_role(role_id, pool)
    return {"items": [m.to_dict() for m in matches]}


@router.get("/demo-pool")
async def pool(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Candidate pool for marketplace ranking — org employees (path kept for FE)."""
    return {"items": await _employee_pool(db, actor.org_id)}
