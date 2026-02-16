
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

async def record_decision(db: AsyncSession, org_id, decision_type, entity_type, entity_id,
                          actors, ai_involvement, policies, rationale, evidence):
    await db.execute(text("""
      insert into human_decision_ledger
      (org_id, decision_type, entity_type, entity_id, actors, ai_involvement, policies_applied, rationale, evidence_refs)
      values (:o,:dt,:et,:eid,:a::jsonb,:ai::jsonb,:p::jsonb,:r,:e::jsonb)
    """), {
        "o": org_id, "dt": decision_type, "et": entity_type, "eid": entity_id,
        "a": json.dumps(actors), "ai": json.dumps(ai_involvement),
        "p": json.dumps(policies), "r": rationale, "e": json.dumps(evidence)
    })
