"""
Test resume screening endpoint (#115)
"""
import asyncio
import json
from app.ai.screening import screen

def run_tests():
    print("🧪 Testing AI Resume Screening...\n")
    passed = 0
    failed = 0

    def test(name, result, condition):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name} — got: {result}")
            failed += 1

    # Test 1: Strong match
    print("📋 Test 1: Strong match resume")
    r = screen(
        "Python developer with FastAPI, PostgreSQL, Docker, AWS, SQL, communication, leadership, agile, scrum",
        "Python FastAPI Docker SQL communication agile"
    )
    test("Score is > 0", r, r["score"] > 0)
    test("Match percent > 50%", r, r["match_percent"] > 50)
    test("Has reason", r, len(r["reason"]) > 0)
    test("Has matched keywords", r, len(r["matched_keywords"]) > 0)

    # Test 2: Weak match
    print("\n📋 Test 2: Weak match resume")
    r = screen(
        "Experienced chef with cooking, baking, and restaurant management skills",
        "Python developer with FastAPI, Docker, SQL, and AWS experience required"
    )
    test("Score is low (< 5)", r, r["score"] < 5)
    test("Match percent < 50%", r, r["match_percent"] < 50)

    # Test 3: Empty resume
    print("\n📋 Test 3: Empty inputs")
    r = screen("", "Python developer needed")
    test("Handles empty resume", r, r["score"] == 0)

    r = screen("Python developer", "")
    test("Handles empty criteria", r, r["score"] == 0)

    # Test 4: Bias detection
    print("\n📋 Test 4: Bias detection")
    resume_with_bias = "Female candidate, age 25, married, Python developer with FastAPI skills"
    criteria = "Python developer with FastAPI experience"
    r = screen(resume_with_bias, criteria)
    test("Returns valid score even with sensitive terms", r, r["score"] >= 0)

    # Test 5: Score range validation
    print("\n📋 Test 5: Score range validation")
    r = screen(
        "Python Java SQL Docker AWS FastAPI React Node communication leadership agile",
        "Python SQL Docker AWS communication agile"
    )
    test("Score between 0 and 10", r, 0 <= r["score"] <= 10)
    test("Match percent between 0 and 100", r, 0 <= r["match_percent"] <= 100)

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("✅ All screening tests passed!")
    else:
        print(f"⚠️  {failed} test(s) failed")

if __name__ == "__main__":
    run_tests()
