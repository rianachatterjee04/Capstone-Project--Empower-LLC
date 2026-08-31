"""Enhanced AI resume screening endpoints.

Built on top of app.services.resume_matching_service. Provides:
- POST /resume-ai/match           : score a single resume against a JD
- POST /resume-ai/rank             : rank a list of resumes against one JD
- POST /resume-ai/screen-job/{job} : rank every candidate in the org for one job

Each endpoint writes a defensible record to public.ai_decisions when the table
exists (best effort — does not crash if not present), plus an AuditEvent.
"""
from __future__ import annotations

import json
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent, Candidate, JobPosting
from app.services.resume_matching_service import match_resume, rank_candidates

router = APIRouter(prefix="/resume-ai", tags=["resume-ai"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager")


async def _safe_log_decision(db: AsyncSession, org_id: str, kind: str, inputs: dict, outputs: dict) -> str | None:
    """Best-effort decision logging — savepoint-wrapped so a failure here can
    never poison the caller's parent transaction.
    """
    decision_id = uuid.uuid4()
    try:
        async with db.begin_nested():
            await db.execute(
                text(
                    """
                    insert into public.ai_decisions(
                        id, org_id, decision_type, entity_type, entity_id,
                        inputs, outputs, created_at
                    )
                    values (:id, :org_id, :kind, 'candidate', :entity_id,
                            :inputs, :outputs, now())
                    """
                ),
                {
                    "id": decision_id,
                    "org_id": org_id,
                    "kind": kind,
                    "entity_id": inputs.get("candidate_id"),
                    "inputs": json.dumps(inputs),
                    "outputs": json.dumps(outputs),
                },
            )
        return str(decision_id)
    except Exception:
        return None


@router.post("/match")
async def match_one(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    resume_text = payload.get("resume_text") or ""
    job_description = payload.get("job_description") or ""
    if not resume_text or not job_description:
        raise HTTPException(status_code=400, detail="resume_text and job_description required")

    required_skills = payload.get("required_skills") or None
    min_years = payload.get("min_years")

    result = match_resume(
        resume_text=resume_text,
        job_description=job_description,
        required_skills=required_skills,
        min_years=min_years,
    ).to_dict()

    decision_id = await _safe_log_decision(
        db,
        org_id=actor.org_id,
        kind="resume_match",
        inputs={
            "candidate_id": payload.get("candidate_id"),
            "job_id": payload.get("job_id"),
            "resume_text": resume_text[:20000],
            "job_description": job_description[:20000],
            "required_skills": required_skills,
            "min_years": min_years,
        },
        outputs=result,
    )

    try:
        db.add(
            AuditEvent(
                org_id=UUID(actor.org_id),
                actor_user_id=UUID(actor.user_id),
                actor_role=actor.role,
                event_type="resume_ai.match",
                entity_type="candidate",
                entity_id=UUID(payload["candidate_id"]) if payload.get("candidate_id") else None,
                payload={
                    "job_id": payload.get("job_id"),
                    "score": result["overall_score"],
                    "recommendation": result["recommendation"],
                },
            )
        )
    except Exception:
        pass

    await db.commit()
    return {**result, "decision_id": decision_id}


@router.post("/rank")
async def rank_inline(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Rank a free-form list of candidate payloads.

    payload = {
      "job_description": "...",
      "candidates": [{"id": "...", "name": "...", "resume_text": "..."}, ...],
      "required_skills": [...],
      "min_years": 3
    }
    """
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    job_description = payload.get("job_description") or ""
    candidates = payload.get("candidates") or []
    if not job_description or not candidates:
        raise HTTPException(status_code=400, detail="job_description and candidates required")

    ranked = rank_candidates(
        job_description=job_description,
        candidates=candidates,
        required_skills=payload.get("required_skills") or None,
        min_years=payload.get("min_years"),
    )

    await _safe_log_decision(
        db,
        org_id=actor.org_id,
        kind="resume_rank",
        inputs={"job_description": job_description[:20000], "n": len(candidates)},
        outputs={"top": [c["match"]["overall_score"] for c in ranked[:10]]},
    )
    await db.commit()
    return {"items": ranked}


@router.post("/screen-job/{job_id}")
async def screen_job(
    job_id: str,
    payload: dict | None = None,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Run AI ranking across every stored candidate for the given job posting."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    try:
        job_uuid = UUID(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    org_uuid = UUID(actor.org_id)
    job = (
        await db.execute(
            select(JobPosting).where(JobPosting.id == job_uuid, JobPosting.org_id == org_uuid)
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cands_q = await db.execute(
        select(Candidate).where(
            Candidate.org_id == org_uuid,
            Candidate.job_posting_id == job_uuid,
        )
    )
    cands = cands_q.scalars().all()

    payload = payload or {}
    candidates_payload = [
        {
            "id": str(c.id),
            "name": c.full_name,
            "email": c.email,
            "status": c.status,
            "resume_text": c.resume_text or "",
        }
        for c in cands
    ]
    ranked = rank_candidates(
        job_description=job.description,
        candidates=candidates_payload,
        required_skills=payload.get("required_skills") or None,
        min_years=payload.get("min_years"),
    )

    # persist top-line scores onto the Candidate rows so the UI can re-use them
    for row in ranked:
        try:
            cand_id = UUID(row["id"])
            cand = await db.get(Candidate, cand_id)
            if cand:
                cand.ai_score = row["match"]["overall_score"]
                cand.ai_summary = row["match"]["explanation"][:1000]
        except Exception:
            continue

    await _safe_log_decision(
        db,
        org_id=actor.org_id,
        kind="resume_rank_job",
        inputs={"job_id": str(job_uuid), "n": len(candidates_payload)},
        outputs={"top_scores": [r["match"]["overall_score"] for r in ranked[:10]]},
    )

    db.add(
        AuditEvent(
            org_id=org_uuid,
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="resume_ai.screen_job",
            entity_type="job_posting",
            entity_id=job_uuid,
            payload={"n_candidates": len(candidates_payload)},
        )
    )
    await db.commit()
    return {"job": {"id": str(job.id), "title": job.title}, "items": ranked}
