from sqlalchemy import text
from datetime import datetime, timedelta


async def onboarding_stalled(db):
    rows = (await db.execute(text("""
        select employee_id, created_at
        from onboarding_packets
        where status != 'completed'
        and created_at < now() - interval '3 days'
    """))).mappings().all()

    return [{
        "type": "onboarding_stalled",
        "employee_id": r["employee_id"],
        "message": "Employee has not completed onboarding after 3 days"
    } for r in rows]


async def review_conflict(db):
    rows = (await db.execute(text("""
        select id, ai_flags
        from performance_reviews
        where status='finalized'
        and ai_flags::text like '%discrepancy%'
    """))).mappings().all()

    return [{
        "type": "review_bias_risk",
        "review_id": r["id"],
        "message": "Manager review conflicts with self review"
    } for r in rows]


async def high_risk_case(db):
    rows = (await db.execute(text("""
        select id, created_at
        from cases
        where severity in ('high','critical')
        and status='reported'
        and created_at < now() - interval '24 hours'
    """))).mappings().all()

    return [{
        "type": "legal_risk",
        "case_id": r["id"],
        "message": "High severity case not acknowledged within SLA"
    } for r in rows]


async def run_all_detectors(db):
    findings = []
    findings += await onboarding_stalled(db)
    findings += await review_conflict(db)
    findings += await high_risk_case(db)
    return findings

