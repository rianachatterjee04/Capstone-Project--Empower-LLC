"""
Data validation constraints for the database.
"""
import asyncio
from app.db.session import engine
from sqlalchemy import text

async def add_constraints():
    async with engine.begin() as conn:
        print("🔒 Adding data validation constraints...")

        constraints = [
            ("chk_employee_status", "employees", "status IN ('invited', 'active', 'inactive', 'terminated')"),
            ("chk_employee_email", "employees", "email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'"),
            ("chk_case_status", "cases", "status IN ('open', 'investigating', 'resolved', 'closed')"),
            ("chk_case_severity", "cases", "severity IN ('low', 'medium', 'high', 'critical')"),
            ("chk_case_escalation", "cases", "escalation_level >= 0"),
            ("chk_job_status", "job_postings", "status IN ('draft', 'open', 'closed', 'filled')"),
            ("chk_candidate_status", "candidates", "status IN ('new', 'screened', 'interview', 'rejected', 'hired')"),
            ("chk_candidate_score", "candidates", "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)"),
            ("chk_sla_minutes", "escalation_rules", "sla_minutes > 0"),
            ("chk_policy_status", "policies", "status IN ('draft', 'active', 'archived')"),
            ("chk_policy_version", "policies", "version > 0"),
        ]

        for name, table, check in constraints:
            try:
                # Drop if exists first then recreate
                await conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"))
                await conn.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({check})"))
                print(f"  ✅ {name}")
            except Exception as e:
                print(f"  ⚠️  {name}: {str(e)[:60]}")

        print("✅ All constraints added!")

if __name__ == "__main__":
    asyncio.run(add_constraints())
