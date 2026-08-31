from sqlalchemy import text
import json


async def remember(db, org_id, event, decision):
    await db.execute(text("""
        insert into public.ai_decisions(org_id, decision_type, input, output)
        values (:org_id, :decision_type, :input, :output)
    """), {
        "org_id": org_id,
        "decision_type": event,
        "input": json.dumps({}),
        "output": json.dumps({
            "action": decision.action,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "metadata": decision.metadata,
        }),
    })
    await db.commit()