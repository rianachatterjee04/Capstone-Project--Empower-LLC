
from sqlalchemy import text

async def check_precedent(db, org_id, decision_type, features):
    rows = await db.execute(text("""
      select outcome, pattern from decision_precedents
      where org_id=:o and decision_type=:d
    """), {"o":org_id,"d":decision_type})
    alerts=[]
    for r in rows:
        if r.pattern == features:
            alerts.append(r.outcome)
    return alerts
