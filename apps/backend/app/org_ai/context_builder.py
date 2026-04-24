from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from .types import OrgContext


async def build_context(db: AsyncSession, org_id: str, event: str, payload: dict) -> OrgContext:
    """
    Builds a hierarchical organizational snapshot for OrgAI reasoning.
    This is the single most important input to the decision engine.
    """

    employee_id = payload.get("employee_id")
    case_id = payload.get("case_id")

    employee = None
    manager = None
    team = []
    history = []
    org_stats = {}
    open_cases = []
    reviews = []

    # -----------------------------------------------------
    # SUBJECT (employee)
    # -----------------------------------------------------
    if employee_id:
        employee = (await db.execute(text("""
            select id, manager_employee_id, job_title, status, start_date
            from public.employees
            where id=:id and org_id=:org
        """), {"id": employee_id, "org": org_id})).mappings().first()

        if employee:

            # manager
            if employee["manager_employee_id"]:
                manager = (await db.execute(text("""
                    select id, job_title
                    from public.employees
                    where id=:id and org_id=:org
                """), {"id": employee["manager_employee_id"], "org": org_id})).mappings().first()

            # teammates
            team = (await db.execute(text("""
                select id, job_title, status
                from public.employees
                where manager_employee_id=:mid and org_id=:org
            """), {"mid": employee["manager_employee_id"], "org": org_id})).mappings().all()

            # audit history
            history = (await db.execute(text("""
                select event_type, payload, created_at
                from public.audit_events
                where entity_id=:eid
                order by created_at desc
                limit 100
            """), {"eid": employee_id})).mappings().all()

    # -----------------------------------------------------
    # ORGANIZATION SNAPSHOT
    # -----------------------------------------------------
    org_stats = (await db.execute(text("""
        select
            count(*) as headcount,
            count(*) filter (where status='active') as active_employees
        from public.employees
        where org_id=:org
    """), {"org": org_id})).mappings().first()

    # open investigations
    open_cases = (await db.execute(text("""
        select id, severity, category, status
        from public.cases
        where org_id=:org and status!='closed'
    """), {"org": org_id})).mappings().all()

    # finalized reviews
    reviews = (await db.execute(text("""
        select employee_id, rating, status, manager_summary
        from public.performance_reviews
        where org_id=:org and status='finalized'
    """), {"org": org_id})).mappings().all()

    # -----------------------------------------------------
    # BUILD CONTEXT OBJECT
    # -----------------------------------------------------
    return OrgContext(
        org_id=str(org_id),
        event=event,
        payload=payload,
        employee=dict(employee) if employee else None,
        manager=dict(manager) if manager else None,
        team=[dict(t) for t in team],
        history=[dict(h) for h in history],
        org_snapshot=dict(org_stats) if org_stats else {},
        open_cases=[dict(c) for c in open_cases],
        reviews=[dict(r) for r in reviews],
        # aliases for simulator.py
        employees=[dict(t) for t in team],  # team members as employee list
        cases=[dict(c) for c in open_cases],
    )