"""Engagement / eNPS pulse-survey router.

Thin router over engagement_service (in-process, org-scoped), mirroring the
goals.py / recognition.py pattern. Anonymous surveys never surface individual
responses; aggregates enforce k-anonymity.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services import engagement_service as svc


router = APIRouter(prefix="/engagement", tags=["engagement"])

_ADMIN = ("owner", "admin", "hr", "manager")


# --- Survey CRUD ------------------------------------------------------------
@router.get("/surveys")
async def list_surveys(actor: Actor = Depends(require_org)):
    return svc.list_surveys(actor.org_id)


@router.get("/surveys/{survey_id}")
async def get_survey(survey_id: str, actor: Actor = Depends(require_org)):
    out = svc.get_survey(actor.org_id, survey_id)
    if not out:
        raise HTTPException(status_code=404, detail="Survey not found")
    return out


@router.post("/surveys")
async def create_survey(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.create_survey(actor.org_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="title required")
    return out


@router.post("/surveys/{survey_id}/questions")
async def add_question(survey_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.add_question(actor.org_id, survey_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="text and valid kind required")
    return out


@router.post("/surveys/{survey_id}/open")
async def open_survey(survey_id: str, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.set_status(actor.org_id, survey_id, "open")
    if not out:
        raise HTTPException(status_code=404, detail="Survey not found")
    return out


@router.post("/surveys/{survey_id}/close")
async def close_survey(survey_id: str, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.set_status(actor.org_id, survey_id, "closed")
    if not out:
        raise HTTPException(status_code=404, detail="Survey not found")
    return out


# --- Responses --------------------------------------------------------------
@router.post("/surveys/{survey_id}/responses")
async def submit_response(survey_id: str, payload: dict, actor: Actor = Depends(require_org)):
    """Any org member may submit. Anonymity is enforced by the survey flag."""
    out = svc.submit_response(actor.org_id, survey_id, actor.user_id, payload.get("answers") or {})
    if out is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    if out.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Survey not found")
    if out.get("error") == "not_open":
        raise HTTPException(status_code=400, detail="Survey is not open")
    if out.get("error"):
        raise HTTPException(status_code=400, detail="No valid answers")
    return out


# --- Aggregates -------------------------------------------------------------
@router.get("/surveys/{survey_id}/results")
async def results(survey_id: str, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.results(actor.org_id, survey_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    return out


@router.get("/surveys/{survey_id}/insights")
async def insights(survey_id: str, actor: Actor = Depends(require_org)):
    if actor.role not in _ADMIN:
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.insights(actor.org_id, survey_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    return out
