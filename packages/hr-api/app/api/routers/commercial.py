"""The commercial loop, as an API: what we did, who it produced, what it made.

The loop used to exist only inside a demo script. It printed a convincing story
and persisted nothing, so there was no way to open it, no way to check it weeks
later, and no way for a second load from the same customer to change the
answer. A narration is not a product.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.commercial import loop as L

router = APIRouter(prefix="/commercial", tags=["commercial"])

OPS_ROLES = ("owner", "admin", "hr", "recruiter", "manager")


def _require_ops(actor: Actor) -> None:
    if getattr(actor, "role", None) not in OPS_ROLES:
        raise HTTPException(
            status_code=403,
            detail="The commercial loop is a staff surface")


def _j(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = int(v) if v == v.to_integral_value() else float(v)
        elif isinstance(v, UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


async def _chain(db: AsyncSession, org, prospect_id) -> dict:
    """One prospect's whole chain, freshly attributed."""
    p = (await db.execute(text("""
        SELECT p.*, s.name AS source_name, s.kind AS source_kind,
               s.permits_direct_marketing, s.licence_note,
               c.name AS customer_name
        FROM public.commercial_prospects p
        JOIN public.commercial_sources s
          ON s.id = p.source_id AND s.org_id = p.org_id
        LEFT JOIN public.trucking_customers c
          ON c.id = p.customer_id AND c.org_id = p.org_id
        WHERE p.org_id = :o AND p.id = :i"""),
        {"o": org, "i": prospect_id})).mappings().first()
    if p is None:
        raise HTTPException(status_code=404, detail="no such prospect")

    actions = (await db.execute(text("""
        SELECT id, action_kind, description, occurred_on, spend_cents,
               spend_authority, spend_source_ref, hypothesis
        FROM public.commercial_actions
        WHERE org_id = :o AND prospect_id = :i
        ORDER BY occurred_on"""),
        {"o": org, "i": prospect_id})).mappings().all()

    invoices, costs, loads = [], [], []
    if p["customer_id"]:
        invoices = (await db.execute(text("""
            SELECT id, invoice_number, state, issued_on, due_on,
                   total_cents, paid_cents
            FROM public.trucking_invoices
            WHERE org_id = :o AND customer_id = :c
            ORDER BY issued_on"""),
            {"o": org, "c": p["customer_id"]})).mappings().all()
        costs = (await db.execute(text("""
            SELECT k.id, k.cost_type, k.amount_cents, k.authority
            FROM public.trucking_load_costs k
            JOIN public.trucking_loads l
              ON l.id = k.load_id AND l.org_id = k.org_id
            WHERE k.org_id = :o AND l.customer_id = :c"""),
            {"o": org, "c": p["customer_id"]})).mappings().all()
        loads = (await db.execute(text("""
            SELECT id, load_number, status, customer_rate_cents,
                   origin_city, origin_state, destination_city,
                   destination_state
            FROM public.trucking_loads
            WHERE org_id = :o AND customer_id = :c
            ORDER BY load_number"""),
            {"o": org, "c": p["customer_id"]})).mappings().all()

    attribution = L.attribute(
        actions=[type("A", (), dict(a))() for a in actions],
        invoices=[type("I", (), dict(i))() for i in invoices],
        costs=[type("C", (), dict(c))() for c in costs],
        loads_count=len(loads))

    source = type("S", (), {
        "name": p["source_name"], "kind": p["source_kind"],
        "permits_direct_marketing": p["permits_direct_marketing"],
        "licence_note": p["licence_note"]})()
    rights = L.check_marketing_allowed(source=source)

    return {
        "prospect": {
            "id": str(p["id"]), "name": p["name"], "stage": p["stage"],
            "city": p["city"], "state": p["state"],
            "identity_strength": p["identity_strength"],
            "saved_by": p["saved_by"],
            "saved_at": p["saved_at"].isoformat() if p["saved_at"] else None,
            "customer_id": str(p["customer_id"]) if p["customer_id"] else None,
            "customer_name": p["customer_name"],
        },
        "source": {
            "name": p["source_name"], "kind": p["source_kind"],
            "permits_direct_marketing": p["permits_direct_marketing"],
            "licence_note": p["licence_note"],
        },
        "marketing_rights": {
            "allowed": rights.allowed,
            "refusal_code": rights.refusal_code,
            "reason": rights.reason,
            "alternative": rights.alternative,
        },
        "actions": [_j(dict(a)) for a in actions],
        "loads": [_j(dict(x)) for x in loads],
        "invoices": [_j(dict(i)) for i in invoices],
        "costs": [_j(dict(c)) for c in costs],
        "attribution": attribution.as_dict(),
    }


@router.get("/loop")
async def loop_index(actor: Actor = Depends(require_org),
                     db: AsyncSession = Depends(db_session)) -> dict:
    """Every prospect a human has saved, with what it has produced so far."""
    _require_ops(actor)
    rows = (await db.execute(text("""
        SELECT p.id, p.name, p.stage, p.city, p.state, p.saved_by,
               s.name AS source_name, s.permits_direct_marketing,
               c.name AS customer_name,
               (SELECT COALESCE(SUM(a.spend_cents), 0)
                  FROM public.commercial_actions a
                 WHERE a.prospect_id = p.id) AS spend_cents,
               (SELECT count(*) FROM public.trucking_loads l
                 WHERE l.customer_id = p.customer_id
                   AND l.org_id = p.org_id) AS loads_count
        FROM public.commercial_prospects p
        JOIN public.commercial_sources s
          ON s.id = p.source_id AND s.org_id = p.org_id
        LEFT JOIN public.trucking_customers c
          ON c.id = p.customer_id AND c.org_id = p.org_id
        WHERE p.org_id = :o
        ORDER BY p.created_at DESC"""), {"o": actor.org_id})).mappings().all()

    return {
        "prospects": [
            {**_j(dict(r)), "href": f"/api/commercial/loop/{r['id']}"}
            for r in rows],
        "note": ("A prospect appears here because a person saved it. Nothing "
                 "in this system turns an observation into a lead on its own."),
    }


@router.get("/loop/{prospect_id}")
async def loop_detail(prospect_id: UUID,
                      actor: Actor = Depends(require_org),
                      db: AsyncSession = Depends(db_session)) -> dict:
    _require_ops(actor)
    return await _chain(db, actor.org_id, prospect_id)


@router.post("/prospects/{prospect_id}/actions")
async def record_action(prospect_id: UUID, payload: Dict[str, Any],
                        actor: Actor = Depends(require_org),
                        db: AsyncSession = Depends(db_session)) -> dict:
    """Record something we did, and what it cost.

    Refused when the prospect's source does not licence outreach, or when no
    human has saved the prospect. Both refusals happen BEFORE the spend is
    recorded -- a spend row against a prospect we may not contact is a record
    of having done it.
    """
    _require_ops(actor)
    p = (await db.execute(text("""
        SELECT p.stage, s.name AS source_name, s.kind AS source_kind,
               s.permits_direct_marketing, s.licence_note
        FROM public.commercial_prospects p
        JOIN public.commercial_sources s
          ON s.id = p.source_id AND s.org_id = p.org_id
        WHERE p.org_id = :o AND p.id = :i"""),
        {"o": actor.org_id, "i": prospect_id})).mappings().first()
    if p is None:
        raise HTTPException(status_code=404, detail="no such prospect")

    source = type("S", (), {
        "name": p["source_name"], "kind": p["source_kind"],
        "permits_direct_marketing": p["permits_direct_marketing"],
        "licence_note": p["licence_note"]})()
    try:
        L.check_action(source=source, prospect_stage=p["stage"])
    except L.LoopRefused as exc:
        raise HTTPException(status_code=409,
                            detail={"code": exc.code, "detail": exc.detail})

    kind = (payload.get("action_kind") or "").upper()
    authority = (payload.get("spend_authority") or "MODELED").upper()
    spend = int(payload.get("spend_cents") or 0)
    ref = payload.get("spend_source_ref")
    if authority == "FINANCIAL_ACTUAL" and not ref:
        raise HTTPException(
            status_code=422,
            detail=("a FINANCIAL_ACTUAL spend has to cite the invoice or "
                    "statement it came from"))

    aid = uuid.uuid4()
    try:
        await db.execute(text("""INSERT INTO public.commercial_actions
            (id,org_id,prospect_id,action_kind,description,occurred_on,
             spend_cents,spend_authority,spend_source_ref,hypothesis)
            VALUES (:i,:o,:p,:k,:d,:on,:s,:a,:r,:h)"""),
            {"i": aid, "o": actor.org_id, "p": prospect_id, "k": kind,
             "d": (payload.get("description") or "").strip() or kind,
             "on": payload.get("occurred_on") or date.today(),
             "s": spend, "a": authority, "r": ref,
             "h": payload.get("hypothesis")})
        await db.commit()
    except Exception as exc:            # constraint refusals reach the caller
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc).split("\n")[0])

    return {"id": str(aid), "action_kind": kind, "spend_cents": spend,
            "spend_authority": authority}


@router.post("/prospects/{prospect_id}/stage")
async def advance_stage(prospect_id: UUID, payload: Dict[str, Any],
                        actor: Actor = Depends(require_org),
                        db: AsyncSession = Depends(db_session)) -> dict:
    """Move a prospect along, with the human who decided it."""
    _require_ops(actor)
    row = (await db.execute(text("""
        SELECT stage, saved_by FROM public.commercial_prospects
        WHERE org_id = :o AND id = :i"""),
        {"o": actor.org_id, "i": prospect_id})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="no such prospect")

    target = (payload.get("stage") or "").upper()
    saved_by = (payload.get("saved_by") or row["saved_by"] or "").strip()
    try:
        L.check_stage_change(current=row["stage"], target=target,
                             saved_by=saved_by)
    except L.LoopRefused as exc:
        raise HTTPException(status_code=409,
                            detail={"code": exc.code, "detail": exc.detail})

    await db.execute(text("""UPDATE public.commercial_prospects
        SET stage = :s,
            saved_by = COALESCE(saved_by, :by),
            saved_at = COALESCE(saved_at, now())
        WHERE org_id = :o AND id = :i"""),
        {"s": target, "by": saved_by, "o": actor.org_id, "i": prospect_id})
    await db.commit()
    return {"id": str(prospect_id), "stage": target, "saved_by": saved_by}
