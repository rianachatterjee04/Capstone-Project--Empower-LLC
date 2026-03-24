import asyncio
from app.db.session import engine
from sqlalchemy import text

async def add_indexes():
    async with engine.begin() as conn:
        print("📊 Adding indexes on frequently queried columns...")

        indexes = [
            # Employees
            "CREATE INDEX IF NOT EXISTS idx_employees_org_id ON employees(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status)",
            "CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department)",
            "CREATE INDEX IF NOT EXISTS idx_employees_email ON employees(email)",

            # Cases
            "CREATE INDEX IF NOT EXISTS idx_cases_org_id ON cases(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)",
            "CREATE INDEX IF NOT EXISTS idx_cases_severity ON cases(severity)",
            "CREATE INDEX IF NOT EXISTS idx_cases_category ON cases(category)",

            # Job postings
            "CREATE INDEX IF NOT EXISTS idx_job_postings_org_id ON job_postings(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_job_postings_status ON job_postings(status)",

            # Candidates
            "CREATE INDEX IF NOT EXISTS idx_candidates_org_id ON candidates(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status)",
            "CREATE INDEX IF NOT EXISTS idx_candidates_job_posting_id ON candidates(job_posting_id)",

            # Escalation rules
            "CREATE INDEX IF NOT EXISTS idx_escalation_rules_org_id ON escalation_rules(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_escalation_rules_is_active ON escalation_rules(is_active)",

            # Escalations
            "CREATE INDEX IF NOT EXISTS idx_escalations_org_id ON escalations(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status)",
            "CREATE INDEX IF NOT EXISTS idx_escalations_entity_type ON escalations(entity_type)",

            # Audit events
            "CREATE INDEX IF NOT EXISTS idx_audit_events_org_id ON audit_events(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_event_type ON audit_events(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at)",

            # Policies
            "CREATE INDEX IF NOT EXISTS idx_policies_org_id ON policies(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status)",

            # Onboarding packets
            "CREATE INDEX IF NOT EXISTS idx_onboarding_packets_org_id ON onboarding_packets(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_onboarding_packets_status ON onboarding_packets(status)",
            "CREATE INDEX IF NOT EXISTS idx_onboarding_packets_employee_id ON onboarding_packets(employee_id)",

            # Benefit plans
            "CREATE INDEX IF NOT EXISTS idx_benefit_plans_org_id ON benefit_plans(org_id)",
            "CREATE INDEX IF NOT EXISTS idx_benefit_plans_category ON benefit_plans(category)",
        ]

        for idx in indexes:
            try:
                await conn.execute(text(idx))
                name = idx.split("idx_")[1].split(" ")[0]
                print(f"  ✅ idx_{name}")
            except Exception as e:
                print(f"  ⚠️  {idx[:60]}... — {e}")

        print("✅ All indexes created!")

if __name__ == "__main__":
    asyncio.run(add_indexes())
