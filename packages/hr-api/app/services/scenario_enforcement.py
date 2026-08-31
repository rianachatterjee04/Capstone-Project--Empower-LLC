
from sqlalchemy import text

async def enforce_scenario(db, org_id):
    row = await db.execute(text("""
      select constraints from workforce_scenarios
      where org_id=:o and approved=true limit 1
    """), {"o":org_id})
    return row.first()
