from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

from app.services.llm import llm_complete
from app.services.ai_system_of_record import log_decision

async def get_job_criteria(db: AsyncSession, org_id: UUID, provider: str, job_external_id: str) -> dict:
    row = (await db.execute(text("""
        select criteria from public.ats_job_screening_criteria
        where org_id=:org_id and provider=:provider and job_external_id=:jid
    """), {"org_id": str(org_id), "provider": provider, "jid": job_external_id})).first()
    return row[0] if row else {}

def _build_prompt(criteria: dict, candidate_payload: dict) -> str:
    return f"""You are an expert recruiter.
Criteria (JSON): {json.dumps(criteria)}
Candidate (JSON): {json.dumps(candidate_payload)}

Return JSON with fields:
- score (0-100)
- rationale (short)
"""

async def score_candidate(db: AsyncSession, org_id: UUID, provider: str, candidate_external_id: str, job_external_id: Optional[str]=None) -> dict:
    cand = (await db.execute(text("""
        select payload from public.ats_candidates where org_id=:org_id and provider=:provider and external_id=:cid
    """), {"org_id": str(org_id), "provider": provider, "cid": candidate_external_id})).first()
    if not cand:
        return {"skipped": True, "reason": "candidate_not_found"}
    candidate_payload = cand[0]

    criteria = {}
    if job_external_id:
        criteria = await get_job_criteria(db, org_id, provider, job_external_id)

    prompt = _build_prompt(criteria, candidate_payload)
    out = llm_complete(prompt, system="You are a strict JSON generator.", model=None)
    try:
        data = json.loads(out)
    except Exception:
        data = {"score": 50, "rationale": out[:400]}

    score = float(data.get("score", 50))
    rationale = str(data.get("rationale",""))[:2000]

    await db.execute(text("""
        insert into public.ats_screening_scores(org_id, provider, candidate_external_id, job_external_id, score, rationale, model)
        values (:org_id, :provider, :cid, :jid, :score, :rationale, :model)
        on conflict (org_id, provider, candidate_external_id, job_external_id) do update
        set score=excluded.score, rationale=excluded.rationale, model=excluded.model, created_at=now()
    """), {"org_id": str(org_id), "provider": provider, "cid": candidate_external_id, "jid": job_external_id,
             "score": score, "rationale": rationale, "model": "llm"} )

    await log_decision(
        db=db, org_id=org_id, actor_user_id=None, actor_role="system",
        decision_type="ats.screening.score", entity_type="candidate",
        entity_id=None, input_payload={"criteria": criteria}, output_payload={"score": score, "rationale": rationale},
        model="llm"
    )
    return {"score": score, "rationale": rationale}
