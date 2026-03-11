from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.json_utils import json_safe
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.services.policy_dsl import english_to_dsl
from app.services.policy_dsl_v2 import parse_policy, dry_run
from app.db.models import AuditEvent

router = APIRouter(prefix="/policy", tags=["policy-sandbox"])


# ---------------------------------------------------------
# Parse English → DSL (Preview only)
# ---------------------------------------------------------
@router.post("/preview")
async def preview(payload: dict, actor: Actor = Depends(require_org)):
    """
    Converts HR written English policy into DSL without saving.
    Used by UI live editor.
    """

    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    try:
        parsed = english_to_dsl("preview", text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"parse_error: {str(e)}")

    return {
        "dsl": parsed.dsl,
        "normalized_body": parsed.body,
        "warnings": parsed.warnings if hasattr(parsed, "warnings") else []
    }


# ---------------------------------------------------------
# Advanced Rule Extraction
# ---------------------------------------------------------
@router.post("/extract-rules")
async def extract_rules(payload: dict, actor: Actor = Depends(require_org)):
    """
    Returns structured rule objects for visualization graph UI
    """

    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    rules = parse_policy(text)
    return {"rules": rules}


# ---------------------------------------------------------
# Dry Run Policy Against Real Scenario
# ---------------------------------------------------------
@router.post("/simulate")
async def simulate(payload: dict, actor: Actor = Depends(require_org)):
    """
    Simulates a policy decision using provided context.
    Example: PTO request, termination, escalation
    """

    policy_text = payload.get("policy_text")
    context = payload.get("context") or {}

    if not policy_text:
        raise HTTPException(status_code=400, detail="policy_text required")

    rules = parse_policy(policy_text)
    results = dry_run(rules, context)

    return {
        "decision": results,
        "explanation": results.get("explanation"),
        "triggered_rules": results.get("triggered_rules")
    }


# ---------------------------------------------------------
# Explain Existing Stored Policy
# ---------------------------------------------------------
@router.get("/explain/{policy_id}")
async def explain(policy_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    row = (await db.execute(text("""
        select name, body, dsl
        from public.policies
        where id=:id and org_id=:org_id
    """), {"id": policy_id, "org_id": actor.org_id})).first()

    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")

    name, body, dsl_data = row

    return {
        "name": name,
        "human_readable": body,
        "dsl": dsl_data,
        "summary": f"This policy contains {len(json.loads(dsl_data or '[]'))} rules"
    }


# ---------------------------------------------------------
# Validate Policy Safety (Pre-activation guard)
# ---------------------------------------------------------
@router.post("/validate")
async def validate(payload: dict, actor: Actor = Depends(require_org)):

    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    rules = parse_policy(text)

    dangerous = []
    for r in rules:
        if "terminate" in json.dumps(r).lower() and "without approval" in json.dumps(r).lower():
            dangerous.append("Termination without approval detected")

    return {
        "valid": len(dangerous) == 0,
        "warnings": dangerous,
        "rule_count": len(rules)
    }

