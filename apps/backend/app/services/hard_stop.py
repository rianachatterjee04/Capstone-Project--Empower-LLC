
from sqlalchemy import text

async def check_block(db, org_id, entity_type, entity_id):
    r = await db.execute(text("""
      select 1 from enforcement_blocks
      where org_id=:o and entity_type=:t and entity_id=:i and active=true
    """), {"o":org_id,"t":entity_type,"i":entity_id})
    if r.first():
        raise Exception("Operation blocked by policy enforcement")
