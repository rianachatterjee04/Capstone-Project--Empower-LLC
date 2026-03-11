from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.core.json_utils import json_safe
from app.services.policy_dsl_v2 import dry_run, parse_policy
from app.temporal.client import get_client
from app.temporal.workflows.escalation import EscalationWorkflow

router = APIRouter(prefix="/policies2", tags=["policies2"])


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return None


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("select to_regclass(:table_name)"),
        {"table_name": f"public.{table_name}"},
    )
    return result.scalar() is not None


async def column_exists(db: AsyncSession, table_name: str, column_name: str) -> bool:
    result = await db.execute(
        text("""
            select 1
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
              and column_name = :column_name
            limit 1
        """),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.first() is not None


@router.post("/parse")
async def parse(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rules = parse_policy(payload.get("policy_text", ""))
    return {"rules": rules}


@router.post("/create")
async def create(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    name = payload.get("name")
    policy_text = payload.get("policy_text")

    if not name or not policy_text:
        raise HTTPException(status_code=400, detail="name and policy_text required")

    for table_name in ("policies", "policy_versions", "policy_rules"):
        if not await table_exists(db, table_name):
            raise HTTPException(
                status_code=503,
                detail=f"{table_name} table is not available yet. Run the policies migration first.",
            )

    has_scope = await column_exists(db, "policies", "scope")

    if has_scope:
        pres = await db.execute(
            text("""
                insert into public.policies(org_id, name, scope)
                values (:org_id, :name, :scope)
                returning id
            """),
            {
                "org_id": org_id,
                "name": name,
                "scope": payload.get("scope", "org"),
            },
        )
    else:
        pres = await db.execute(
            text("""
                insert into public.policies(org_id, name)
                values (:org_id, :name)
                returning id
            """),
            {
                "org_id": org_id,
                "name": name,
            },
        )

    pid = pres.scalar()

    vres = await db.execute(
        text("""
            insert into public.policy_versions(
                org_id,
                policy_id,
                version,
                policy_text,
                created_at
            )
            values (
                :org_id,
                :policy_id,
                1,
                :policy_text,
                now()
            )
            returning id
        """),
        {
            "org_id": org_id,
            "policy_id": pid,
            "policy_text": policy_text,
        },
    )
    pvid = vres.scalar()

    rules = parse_policy(policy_text)

    for r in rules:
        await db.execute(
            text("""
                insert into public.policy_rules(org_id, policy_version_id, rule)
                values (:org_id, :pvid, cast(:rule as jsonb))
            """),
            {
                "org_id": org_id,
                "pvid": pvid,
                "rule": json.dumps(json_safe(r)),
            },
        )

    await db.commit()

    return {
        "policy_id": str(pid),
        "policy_version_id": str(pvid),
        "rules_count": len(rules),
    }


@router.post("/dry-run")
async def dry(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rules = parse_policy(payload.get("policy_text", ""))
    results = dry_run(rules, payload.get("context") or {})
    return {"results": results}


@router.post("/execute")
async def execute(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)
    if org_id is None or user_id is None:
        raise HTTPException(status_code=400, detail="Missing actor identifiers")

    for table_name in ("policy_rules", "policy_executions"):
        if not await table_exists(db, table_name):
            raise HTTPException(
                status_code=503,
                detail=f"{table_name} table is not available yet. Run the policies migration first.",
            )

    policy_version_id = payload.get("policy_version_id")
    context = payload.get("context") or {}

    if not policy_version_id:
        raise HTTPException(status_code=400, detail="policy_version_id required")

    rows = (
        await db.execute(
            text("""
                select rule
                from public.policy_rules
                where org_id = :org_id and policy_version_id = :pvid
            """),
            {"org_id": org_id, "pvid": policy_version_id},
        )
    ).fetchall()

    rules = [r[0] for r in rows]
    results = dry_run(rules, context)

    ex = await db.execute(
        text("""
            insert into public.policy_executions(
                org_id,
                policy_version_id,
                context,
                results,
                executed_at,
                executed_by
            )
            values (
                :org_id,
                :pvid,
                cast(:context as jsonb),
                cast(:results as jsonb),
                now(),
                :uid
            )
            returning id
        """),
        {
            "org_id": org_id,
            "pvid": policy_version_id,
            "context": json.dumps(json_safe(context)),
            "results": json.dumps(json_safe(results)),
            "uid": user_id,
        },
    )

    execution_id = ex.scalar()
    await db.commit()

    return {"execution_id": str(execution_id), "results": results}


@router.post("/enforce")
async def enforce(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "policy_executions"):
        raise HTTPException(
            status_code=503,
            detail="policy_executions table is not available yet. Run the policies migration first.",
        )

    execution_id = payload.get("execution_id")

    row = (
        await db.execute(
            text("""
                select results
                from public.policy_executions
                where id = :id and org_id = :org_id
            """),
            {"id": execution_id, "org_id": org_id},
        )
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="execution not found")

    results = row[0] or []
    actions = []

    for r in results:
        if not r.get("violation"):
            continue

        action = r.get("action")

        if action == "freeze_payroll":
            actions.append("payroll_frozen")

        if action == "lock_case":
            if await table_exists(db, "cases"):
                await db.execute(
                    text("""
                        update public.cases
                        set legal_freeze = true
                        where id = :cid and org_id = :org_id
                    """),
                    {"cid": r.get("entity_id"), "org_id": org_id},
                )
                actions.append("case_locked")
            else:
                actions.append("case_lock_skipped_missing_table")

    await db.commit()
    return {"actions": actions}


@router.post("/schedule-escalation")
async def schedule_escalation(
    payload: dict,
    actor: Actor = Depends(require_org),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    case_id = payload.get("case_id")
    sla_hours = int(payload.get("sla_hours", 48))

    if not case_id:
        raise HTTPException(status_code=400, detail="case_id required")

    client = await get_client()
    handle = await client.start_workflow(
        EscalationWorkflow.run,
        actor.org_id,
        case_id,
        sla_hours,
        id=f"escalation-{actor.org_id}-{case_id}",
        task_queue="foundry-people",
    )

    return {"workflow_id": handle.id}
