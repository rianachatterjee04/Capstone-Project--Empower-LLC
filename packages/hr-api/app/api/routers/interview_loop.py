"""Interview Loop Orchestration router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.interview_loop_service import (
    DEFAULT_STAGES,
    calibrate,
    create_loop,
    decide,
    get_loop,
    list_loops,
    schedule_slot,
    submit_scorecard,
)

router = APIRouter(prefix="/interview-loops", tags=["interview-loops"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager")


@router.get("/stages")
async def stages_endpoint(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [{"key": k, "label": lbl, "default_duration_min": d} for k, lbl, d in DEFAULT_STAGES]}


@router.get("")
async def list_endpoint(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [l.to_dict() for l in list_loops(actor.org_id)]}


@router.post("")
async def create_endpoint(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    candidate_name = (payload.get("candidate_name") or "").strip()
    job_title = (payload.get("job_title") or "").strip()
    hiring_manager = (payload.get("hiring_manager") or "").strip()
    if not candidate_name or not job_title:
        raise HTTPException(status_code=400, detail="candidate_name and job_title required")
    panel = payload.get("panel") or []
    if not panel:
        raise HTTPException(status_code=400, detail="panel (at least 1 slot) required")
    loop = create_loop(
        org_id=actor.org_id,
        candidate_name=candidate_name,
        candidate_id=payload.get("candidate_id"),
        job_title=job_title,
        job_id=payload.get("job_id"),
        hiring_manager=hiring_manager,
        panel=panel,
    )
    return loop.to_dict()


@router.get("/{loop_id}")
async def get_endpoint(loop_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    loop = get_loop(actor.org_id, loop_id)
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")
    return {**loop.to_dict(), "calibration": calibrate(loop)}


@router.post("/{loop_id}/slots/{slot_id}/scorecard")
async def scorecard_endpoint(loop_id: str, slot_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    rating = payload.get("rating")
    if rating is None:
        raise HTTPException(status_code=400, detail="rating required (0-4)")
    slot = submit_scorecard(
        actor.org_id, loop_id, slot_id,
        rating=int(rating),
        signals=payload.get("signals") or {},
        strengths=payload.get("strengths") or [],
        concerns=payload.get("concerns") or [],
        notes=(payload.get("notes") or "").strip(),
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    loop = get_loop(actor.org_id, loop_id)
    return {"slot": slot.to_dict(), "calibration": calibrate(loop) if loop else None}


@router.post("/{loop_id}/slots/{slot_id}/schedule")
async def schedule_endpoint(loop_id: str, slot_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    when = (payload.get("scheduled_at") or "").strip()
    if not when:
        raise HTTPException(status_code=400, detail="scheduled_at required (ISO 8601)")
    slot = schedule_slot(actor.org_id, loop_id, slot_id, when)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    return slot.to_dict()


@router.post("/{loop_id}/decide")
async def decide_endpoint(loop_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    decision = (payload.get("decision") or "").strip()
    if decision not in ("advance", "advance_with_caveats", "hold", "decline"):
        raise HTTPException(status_code=400, detail="invalid decision")
    loop = decide(
        actor.org_id, loop_id,
        decision=decision,
        debrief_notes=(payload.get("debrief_notes") or "").strip(),
    )
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")
    return {**loop.to_dict(), "calibration": calibrate(loop)}
