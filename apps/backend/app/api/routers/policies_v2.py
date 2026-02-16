from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json
from datetime import datetime

from app.api.deps import require_org, db_session, Actor
from app.services.policy_dsl_v2 import parse_policy, dry_run
from app.temporal.client import get_client
from app.temporal.workflows.escalation import EscalationWorkflow

router = APIRouter(prefix="/policies2", tags=["policies2"])


# ---------------------------------------------------------
# PARSE POLICY TEXT → RULES
# ---------------------------------------------------------
@router.post("/parse")
async def parse(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rules = parse_policy(payload.get("policy_text",""))
    return {"rules": rules}


# ---------------------------------------------------------
# CREATE POLICY + VERSION + RULES
# ---------------------------------------------------------
@router.post("/create")
async def create(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    name = payload.get("name")
    policy_text = payload.get("policy_text")
    if not name or not policy_text:
        raise HTTPException(status_code=400, detail="name and policy_text required")

    # create policy
    pres = await db.execute(text("""
        insert into public.policies(org_id, name, scope)
        values (:org_id, :name, :scope)
        returning id
    """), {"org_id": actor.org_id, "name": name, "scope": payload.get("scope","org")})
    pid = pres.first()[0]

    # create version
    vres = await db.execute(text("""
        insert into public.policy_versions(org_id, policy_id, version, policy_text, created_at)
        values (:org_id, :policy_id, 1, :policy_text, now())
        returning id
    """), {"org_id": actor.org_id, "policy_id": str(pid), "policy_text": policy_text})
    pvid = vres.first()[0]

    # parse rules
    rules = parse_policy(policy_text)

    for r in rules:
        await db.execute(text("""
            insert into public.policy_rules(org_id, policy_version_id, rule)
            values (:org_id, :pvid, :rule::jsonb)
        """), {"org_id": actor.org_id, "pvid": str(pvid), "rule": json.dumps(r)})

    await db.commit()

    return {"policy_id": str(pid), "policy_version_id": str(pvid), "rules_count": len(rules)}


# ---------------------------------------------------------
# DRY RUN POLICY AGAINST CONTEXT
# ---------------------------------------------------------
@router.post("/dry-run")
async def dry(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rules = parse_policy(payload.get("policy_text",""))
    results = dry_run(rules, payload.get("context") or {})

    return {"results": results}


# ---------------------------------------------------------
# EXECUTE POLICY AGAINST ENTITY (REAL ENFORCEMENT)
# ---------------------------------------------------------
@router.post("/execute")
async def execute(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    policy_version_id = payload.get("policy_version_id")
    context = payload.get("context") or {}

    if not policy_version_id:
        raise HTTPException(status_code=400, detail="policy_version_id required")

    # load rules
    rows = (await db.execute(text("""
        select rule from public.policy_rules
        where org_id=:org_id and policy_version_id=:pvid
    """), {"org_id": actor.org_id, "pvid": policy_version_id})).fetchall()

    rules = [r[0] for r in rows]
    results = dry_run(rules, context)

    # record execution
    ex = await db.execute(text("""
        insert into public.policy_executions(org_id, policy_version_id, context, results, executed_at, executed_by)
        values (:org_id, :pvid, :context::jsonb, :results::jsonb, now(), :uid)
        returning id
    """), {
        "org_id": actor.org_id,
        "pvid": policy_version_id,
        "context": json.dumps(context),
        "results": json.dumps(results),
        "uid": actor.user_id
    })

    execution_id = ex.first()[0]
    await db.commit()

    return {"execution_id": str(execution_id), "results": results}


# ---------------------------------------------------------
# CONSEQUENCE BINDING (AUTOMATIC ACTIONS)
# ---------------------------------------------------------
@router.post("/enforce")
async def enforce(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    execution_id = payload.get("execution_id")

    row = (await db.execute(text("""
        select results from public.policy_executions
        where id=:id and org_id=:org_id
    """), {"id": execution_id, "org_id": actor.org_id})).first()

    if not row:
        raise HTTPException(status_code=404, detail="execution not found")

    results = row[0]

    actions = []

    for r in results:
        if r.get("violation"):
            action = r.get("action")

            if action == "freeze_payroll":
                actions.append("payroll_frozen")

            if action == "lock_case":
                await db.execute(text("""
                    update public.cases set legal_freeze=true
                    where id=:cid and org_id=:org_id
                """), {"cid": r.get("entity_id"), "org_id": actor.org_id})
                actions.append("case_locked")

    await db.commit()
    return {"actions": actions}


# ---------------------------------------------------------
# SCHEDULE SLA ESCALATION
# ---------------------------------------------------------
@router.post("/schedule-escalation")
async def schedule_escalation(payload: dict, actor: Actor = Depends(require_org)):

    if actor.role not in ("owner","admin","hr"):
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

    return {"workflow_id": handle.id, "run_id": handle.result_run_id}

