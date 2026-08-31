"""Candidate Integrity router — fraud / deepfake / proxy detection.

Wired into the recruiting/interview flow. Org-scoped, deterministic, fail-soft.
Mounted at /api/candidate-integrity.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services import candidate_integrity_service as svc


router = APIRouter(prefix="/candidate-integrity", tags=["candidate-integrity"])

_ALLOWED = ("owner", "admin", "hr", "recruiter", "manager")


def _guard(actor: Actor) -> None:
    if actor.role not in _ALLOWED:
        raise HTTPException(status_code=403, detail="Not allowed")


@router.post("/assess")
async def assess(payload: dict, actor: Actor = Depends(require_org)):
    _guard(actor)
    candidate_id = (payload.get("candidate_id") or "").strip()
    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id required")
    return svc.assess(
        actor.org_id,
        candidate_id=candidate_id,
        candidate_name=(payload.get("candidate_name") or "Candidate").strip(),
        signals=payload.get("signals") or {},
        interview_id=payload.get("interview_id"),
        assessed_by=actor.claims.get("email"),
    )


@router.get("/candidate/{candidate_id}")
async def candidate(candidate_id: str, actor: Actor = Depends(require_org)):
    _guard(actor)
    out = svc.get_candidate(actor.org_id, candidate_id)
    if not out:
        raise HTTPException(status_code=404, detail="No integrity assessment for this candidate")
    return out


@router.get("/queue")
async def queue(min_band: str = "review", actor: Actor = Depends(require_org)):
    _guard(actor)
    if min_band not in ("clear", "review", "high_risk"):
        raise HTTPException(status_code=400, detail="min_band must be clear|review|high_risk")
    return svc.review_queue(actor.org_id, min_band=min_band)
