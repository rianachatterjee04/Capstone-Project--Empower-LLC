import asyncio
from app.db.session import engine
from sqlalchemy import text

ORG_ID = "11111111-1111-1111-1111-111111111111"
EMP1 = "aaaa0001-0000-0000-0000-000000000001"

async def seed():
    async with engine.begin() as conn:

        print("🌱 Seeding organization...")
        await conn.execute(text("INSERT INTO orgs (id, name) VALUES (:id, :name) ON CONFLICT DO NOTHING"),
            {"id": ORG_ID, "name": "Empower LLC"})

        print("👥 Seeding employees...")
        employees = [
            (EMP1, "Sarah Chen", "sarah.chen@empower.com", "Engineering Manager", "Engineering"),
            ("aaaa0001-0000-0000-0000-000000000002", "James Patel", "james.patel@empower.com", "Software Engineer", "Engineering"),
            ("aaaa0001-0000-0000-0000-000000000003", "Maria Lopez", "maria.lopez@empower.com", "HR Specialist", "Human Resources"),
            ("aaaa0001-0000-0000-0000-000000000004", "David Kim", "david.kim@empower.com", "Product Manager", "Product"),
            ("aaaa0001-0000-0000-0000-000000000005", "Aisha Johnson", "aisha.johnson@empower.com", "UX Designer", "Product"),
            ("aaaa0001-0000-0000-0000-000000000006", "Tom Williams", "tom.williams@empower.com", "Sales Lead", "Sales"),
            ("aaaa0001-0000-0000-0000-000000000007", "Priya Sharma", "priya.sharma@empower.com", "Sales Representative", "Sales"),
            ("aaaa0001-0000-0000-0000-000000000008", "Carlos Rivera", "carlos.rivera@empower.com", "Finance Analyst", "Finance"),
            ("aaaa0001-0000-0000-0000-000000000009", "Emily Zhang", "emily.zhang@empower.com", "Software Engineer", "Engineering"),
            ("aaaa0001-0000-0000-0000-000000000010", "Michael Brown", "michael.brown@empower.com", "CFO", "Finance"),
        ]
        for emp in employees:
            await conn.execute(text("""
                INSERT INTO employees (id, org_id, legal_name, email, job_title, department, status)
                VALUES (:id, :org_id, :legal_name, :email, :job_title, :department, 'active')
                ON CONFLICT DO NOTHING
            """), {"id": emp[0], "org_id": ORG_ID, "legal_name": emp[1], "email": emp[2],
                   "job_title": emp[3], "department": emp[4]})

        print("📋 Seeding HR cases...")
        cases = [
            ("cccc0001-0000-0000-0000-000000000001", "harassment", "high", "Workplace Harassment Report", "open", 1),
            ("cccc0001-0000-0000-0000-000000000002", "payroll", "medium", "Payroll Discrepancy Q1", "investigating", 1),
            ("cccc0001-0000-0000-0000-000000000003", "safety", "high", "Safety Concern Lab Equipment", "open", 2),
            ("cccc0001-0000-0000-0000-000000000004", "misconduct", "medium", "Employee Misconduct Report", "resolved", 1),
            ("cccc0001-0000-0000-0000-000000000005", "benefits", "low", "Benefits Enrollment Issue", "closed", 1),
        ]
        for case in cases:
            await conn.execute(text("""
                INSERT INTO cases (id, org_id, reporter_employee_id, is_anonymous, category, severity, details, status, escalation_level)
                VALUES (:id, :org_id, :reporter_id, false, :category, :severity, :details, :status, :escalation_level)
                ON CONFLICT DO NOTHING
            """), {"id": case[0], "org_id": ORG_ID, "reporter_id": EMP1,
                   "category": case[1], "severity": case[2], "details": case[3],
                   "status": case[4], "escalation_level": case[5]})

        print("🏥 Seeding benefits plans...")
        plans = [
            ("bbbb0001-0000-0000-0000-000000000001", "Blue Shield PPO", "medical", "Blue Shield", 250.00, 600.00),
            ("bbbb0001-0000-0000-0000-000000000002", "Kaiser HMO", "medical", "Kaiser", 180.00, 500.00),
            ("bbbb0001-0000-0000-0000-000000000003", "Delta Dental Plus", "dental", "Delta Dental", 25.00, 75.00),
            ("bbbb0001-0000-0000-0000-000000000004", "VSP Vision Care", "vision", "VSP", 10.00, 30.00),
            ("bbbb0001-0000-0000-0000-000000000005", "Fidelity 401k", "retirement", "Fidelity", 0.00, 200.00),
        ]
        for plan in plans:
            await conn.execute(text("""
                INSERT INTO benefit_plans (id, org_id, name, category, provider, employee_cost, employer_cost)
                VALUES (:id, :org_id, :name, :category, :provider, :employee_cost, :employer_cost)
                ON CONFLICT DO NOTHING
            """), {"id": plan[0], "org_id": ORG_ID, "name": plan[1], "category": plan[2],
                   "provider": plan[3], "employee_cost": plan[4], "employer_cost": plan[5]})

        print("⚡ Seeding escalation rules...")
        rules = [
            ("eeee0001-0000-0000-0000-000000000001", "High Severity Case Auto-Escalate", "case", True),
            ("eeee0001-0000-0000-0000-000000000002", "PTO Pending Over 48h", "pto", True),
            ("eeee0001-0000-0000-0000-000000000003", "Onboarding Incomplete After 7 Days", "onboarding", True),
            ("eeee0001-0000-0000-0000-000000000004", "Payroll Anomaly Detected", "payroll", False),
        ]
        for rule in rules:
            await conn.execute(text("""
                INSERT INTO escalation_rules (id, org_id, name, entity_type, condition_dsl, sla_minutes, route, is_active)
                VALUES (:id, :org_id, :name, :entity_type, :condition_dsl, :sla_minutes, :route, :is_active)
                ON CONFLICT DO NOTHING
            """), {"id": rule[0], "org_id": ORG_ID, "name": rule[1], "entity_type": rule[2],
                   "condition_dsl": "{}", "sla_minutes": 2880, "route": '{"team": "hr"}', "is_active": rule[3]})

        print("💼 Seeding recruiting jobs...")
        jobs = [
            ("a0000001-0000-0000-0000-000000000001", "Senior Software Engineer", "Remote", "open"),
            ("a0000001-0000-0000-0000-000000000002", "Product Designer", "San Francisco, CA", "open"),
            ("a0000001-0000-0000-0000-000000000003", "Sales Development Rep", "New York, NY", "open"),
            ("a0000001-0000-0000-0000-000000000004", "Data Analyst", "Remote", "draft"),
        ]
        for job in jobs:
            await conn.execute(text("""
                INSERT INTO job_postings (id, org_id, title, location, status, description)
                VALUES (:id, :org_id, :title, :location, :status, :description)
                ON CONFLICT DO NOTHING
            """), {"id": job[0], "org_id": ORG_ID, "title": job[1], "location": job[2],
                   "status": job[3], "description": f"We are looking for a talented {job[1]} to join our team."})

        print("🎯 Seeding candidates...")
        candidates = [
            ("b0000001-0000-0000-0000-000000000001", "Alex Turner", "alex.turner@email.com", "a0000001-0000-0000-0000-000000000001", "interview", 87),
            ("b0000001-0000-0000-0000-000000000002", "Nina Patel", "nina.patel@email.com", "a0000001-0000-0000-0000-000000000001", "screened", 92),
            ("b0000001-0000-0000-0000-000000000003", "Ryan Lee", "ryan.lee@email.com", "a0000001-0000-0000-0000-000000000002", "new", 78),
            ("b0000001-0000-0000-0000-000000000004", "Sofia Martinez", "sofia.m@email.com", "a0000001-0000-0000-0000-000000000003", "hired", 95),
        ]
        for c in candidates:
            await conn.execute(text("""
                INSERT INTO candidates (id, org_id, full_name, email, job_posting_id, status, ai_score, ai_summary)
                VALUES (:id, :org_id, :full_name, :email, :job_id, :status, :score, :summary)
                ON CONFLICT DO NOTHING
            """), {"id": c[0], "org_id": ORG_ID, "full_name": c[1], "email": c[2],
                   "job_id": c[3], "status": c[4], "score": c[5],
                   "summary": f"Strong candidate. AI score: {c[5]}/100."})

        print("✅ Seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed())
