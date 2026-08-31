import asyncio
from app.db.session import engine
from sqlalchemy import text

ORG_ID = "11111111-1111-1111-1111-111111111111"
EMP_ID = "aaaa0001-0000-0000-0000-000000000001"

passed = 0
failed = 0

async def test(name, query, params={}, should_fail=False):
    global passed, failed
    try:
        async with engine.begin() as conn:
            await conn.execute(text(query), params)
        if should_fail:
            print(f"  ❌ {name} — should have failed")
            failed += 1
        else:
            print(f"  ✅ {name}")
            passed += 1
    except Exception as e:
        if should_fail:
            print(f"  ✅ {name} — correctly rejected")
            passed += 1
        else:
            print(f"  ❌ {name} — {str(e)[:80]}")
            failed += 1

async def run_tests():
    print("🧪 Testing data integrity and validation rules...\n")

    print("📋 Employee constraints...")
    await test("Valid employee status", "UPDATE employees SET status = 'active' WHERE id = :id", {"id": EMP_ID})
    await test("Invalid status rejected", "UPDATE employees SET status = 'bad_status' WHERE id = :id", {"id": EMP_ID}, should_fail=True)
    await test("Invalid email rejected", "UPDATE employees SET email = 'not-an-email' WHERE id = :id", {"id": EMP_ID}, should_fail=True)
    await test("Duplicate email rejected", "INSERT INTO employees (id, org_id, legal_name, email, status) VALUES (gen_random_uuid(), :org_id, 'Test', 'sarah.chen@empower.com', 'active')", {"org_id": ORG_ID}, should_fail=True)

    print("\n📋 Case constraints...")
    await test("Valid case severity", "UPDATE cases SET severity = 'high' WHERE org_id = :org_id", {"org_id": ORG_ID})
    await test("Invalid severity rejected", "UPDATE cases SET severity = 'extreme' WHERE org_id = :org_id", {"org_id": ORG_ID}, should_fail=True)
    await test("Valid case status", "UPDATE cases SET status = 'open' WHERE org_id = :org_id", {"org_id": ORG_ID})
    await test("Invalid status rejected", "UPDATE cases SET status = 'pending' WHERE org_id = :org_id", {"org_id": ORG_ID}, should_fail=True)

    print("\n📋 Candidate constraints...")
    await test("Valid AI score", "UPDATE candidates SET ai_score = 85 WHERE org_id = :org_id", {"org_id": ORG_ID})
    await test("Score over 100 rejected", "UPDATE candidates SET ai_score = 150 WHERE org_id = :org_id", {"org_id": ORG_ID}, should_fail=True)
    await test("Negative score rejected", "UPDATE candidates SET ai_score = -5 WHERE org_id = :org_id", {"org_id": ORG_ID}, should_fail=True)
    await test("Invalid candidate status rejected", "UPDATE candidates SET status = 'maybe' WHERE org_id = :org_id", {"org_id": ORG_ID}, should_fail=True)

    print("\n📋 Job posting constraints...")
    await test("Valid job status", "UPDATE job_postings SET status = 'open' WHERE org_id = :org_id", {"org_id": ORG_ID})
    await test("Invalid job status rejected", "UPDATE job_postings SET status = 'expired' WHERE org_id = :org_id", {"org_id": ORG_ID}, should_fail=True)

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("✅ All integrity tests passed!")
    else:
        print(f"⚠️  {failed} test(s) failed")

if __name__ == "__main__":
    asyncio.run(run_tests())
