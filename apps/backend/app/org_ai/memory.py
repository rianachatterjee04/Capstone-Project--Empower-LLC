async def remember(db, org_id, event, decision):
    await db.execute("""
        insert into org_ai_memory(org_id, event, action, confidence)
        values (:o,:e,:a,:c)
    """, {
        "o": org_id,
        "e": event,
        "a": decision.action,
        "c": decision.confidence
    })

