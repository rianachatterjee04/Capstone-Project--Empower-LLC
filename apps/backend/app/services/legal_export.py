
from sqlalchemy import text

async def export_legal_packet(db, org_id, entity_type, entity_id):
    rows = await db.execute(text("""
      select * from human_decision_ledger
      where org_id=:o and entity_type=:t and entity_id=:i
      order by created_at
    """), {"o":org_id,"t":entity_type,"i":entity_id})
    return [dict(r) for r in rows]
