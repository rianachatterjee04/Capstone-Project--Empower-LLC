"""Trucking HTTP surface, including the Today board.

WHAT MAKES THE TODAY BOARD DIFFERENT FROM A DASHBOARD
Every number here can be drilled to the rows it came from, and every number
says what KIND of fact it is. A dashboard that shows "$184K open AR" next to
"$96K projected cash need" without saying that the first is invoiced and the
second is modelled invites a decision that treats them as the same quality of
information.

So each tile carries an `authority` and a `drill` -- the query a person can run
to see the underlying rows. Tiles that cannot be substantiated are not shown as
zero; they are shown as NOT_CONNECTED, because zero is a claim and "we cannot
see this" is a different one.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     UploadFile)
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.trucking import billing as B
from app.trucking import drilldown as DD
from app.trucking import eligibility as EL
from app.trucking import fmcsa_authority as FMCSA
from app.trucking import pod as POD
from app.trucking import rate_confirmation as RC

router = APIRouter(prefix="/trucking", tags=["trucking"])

OPS_ROLES = ("owner", "admin", "hr", "recruiter", "manager")


def _jsonable(row: dict) -> dict:
    """Dates, UUIDs and Decimals, rendered the way the rest of the API does."""
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


def _require_ops(actor: Actor) -> None:
    if getattr(actor, "role", None) not in OPS_ROLES:
        raise HTTPException(status_code=403,
                            detail="Trucking operations is a staff surface")


def _tile(label: str, value: Any, *, authority: str, drill: str,
          hint: str = "", tone: str = "neutral") -> dict:
    """One number, with what kind of fact it is and how to see behind it.

    `drill` used to be a prose description of a SQL predicate -- "trucking
    loads where status is not terminal" -- rendered on a screen shown to a
    buyer. Nothing consumed it and an operator could do nothing with it. It is
    now a KEY into `drilldown.DRILLS`, and `drill_href` is the request that
    returns the actual rows behind this number.
    """
    spec = DD.get(drill)
    if spec is None:                      # pragma: no cover - programming error
        raise HTTPException(
            status_code=500,
            detail=f"tile {label!r} names drill {drill!r}, which does not exist")
    return {"label": label, "value": value, "authority": authority,
            "drill": drill,
            "drill_href": f"/api/trucking/drill/{drill}",
            "drill_action": spec.action,
            "unit": spec.unit,
            "hint": hint, "tone": tone}


def _unconnected_compliance_systems(*, fmcsa_evidenced: bool) -> List[str]:
    """Which compliance systems genuinely are not wired up, for this org.

    FMCSA used to be on this list unconditionally, while `fmcsa_authority` was
    making real requests to the live operating-status dataset. A disclosure
    that is wrong in the CAUTIOUS direction is still wrong, and it teaches a
    buyer that the disclosures here are decoration.

    THE SIGNAL IS EVIDENCE, NOT CONFIGURATION.
    `connectivity()` describes the endpoint -- its URL, its dataset, whether a
    token is needed -- and would say the same thing on a machine with no
    network at all. So it cannot answer this question. What can is whether
    THIS organisation actually holds a carrier whose authority came back from
    FMCSA_LIVE inside the staleness window. That is a real lookup having
    happened, for these carriers, recently.

    Seeded or demo authority never satisfies it: those rows carry
    authority_source = 'SEED', and the caller's query names FMCSA_LIVE
    explicitly.
    """
    missing = ["ELD_HOS", "DRUG_ALCOHOL_CONSORTIUM"]
    if not fmcsa_evidenced:
        missing.insert(0, "FMCSA_LIVE")
    return missing


# ---------------------------------------------------------------------------
# Drill-through
# ---------------------------------------------------------------------------

@router.get("/drill/{key}")
async def drill(key: str, limit: int = 100,
                actor: Actor = Depends(require_org),
                db: AsyncSession = Depends(db_session)) -> dict:
    """The rows behind one Today-board number.

    The predicate is the SAME STRING the tile counted with, so the list and
    the number cannot disagree. `key` indexes a closed registry rather than
    naming a table, and the org filter is part of every predicate rather than
    something the caller supplies -- a drill endpoint that accepted a WHERE
    clause would be a tenant-isolation hole with a friendly name.
    """
    _require_ops(actor)
    spec = DD.get(key)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail=(f"no drill named {key!r}. Available: "
                    f"{', '.join(DD.keys())}"))

    limit = max(1, min(int(limit), 500))
    today_d = date.today()
    binds = {"o": actor.org_id, "d": today_d,
             "soon": today_d + timedelta(days=30)}

    total = (await db.execute(text(spec.count_sql()), binds)).scalar_one()
    rows = (await db.execute(text(spec.rows_sql(limit)), binds)).mappings().all()

    return {
        "key": spec.key,
        "label": spec.label,
        "action": spec.action,
        "unit": spec.unit,
        # The tile's own number, recomputed here from the same predicate. A
        # client can compare it to what it rendered and know immediately if it
        # is showing something stale.
        "tile_value": int(total) if total is not None else 0,
        "returned": len(rows),
        "limit": limit,
        "truncated": len(rows) >= limit,
        "rows": [_jsonable(dict(r)) for r in rows],
        "note": ("These rows come from the same predicate that produced the "
                 "tile. Nothing here is corroborated by a bank, a GL or a "
                 "telematics feed."),
    }


@router.get("/drill")
async def drill_index(actor: Actor = Depends(require_org)) -> dict:
    """Every number on the board that can be opened."""
    _require_ops(actor)
    return {"drills": [
        {"key": d.key, "label": d.label, "unit": d.unit,
         "action": d.action, "href": f"/api/trucking/drill/{d.key}"}
        for d in (DD.DRILLS[k] for k in DD.keys())]}


@router.get("/today")
async def today(actor: Actor = Depends(require_org),
                db: AsyncSession = Depends(db_session)) -> dict:
    """The operating and financial picture, with the authority of each figure."""
    _require_ops(actor)
    org = actor.org_id
    today_d = date.today()

    async def scalar(sql: str, **params) -> Any:
        """A bigint SUM comes back from asyncpg as a string. Returning it
        unconverted made every money tile a string in the JSON, which the UI
        would then have to guess about.

        Extra params are harmless: SQLAlchemy binds only the ones the statement
        names, so passing `d` to a query with no `:d` is not an error.
        """
        res = await db.execute(text(sql), {"o": org, **params})
        v = res.scalar_one()
        return int(v) if v is not None else 0

    # ---- operations and money, from the drills themselves ----------------
    #
    # THE TILE AND THE DRILL-THROUGH RUN THE SAME PREDICATE.
    # These counts used to be written out here as their own SQL, next to a
    # prose `drill` string describing roughly the same thing. Two hand-written
    # queries for one fact drift the moment either is edited, and the operator
    # gets a tile that says 7 and a list with 6 rows in it and no way to tell
    # which is wrong.
    #
    # Now the tile runs `Drill.count_sql()` and the drill-through runs
    # `Drill.rows_sql()` off the same `source` and `where`.
    async def tile_value(key: str) -> int:
        return await scalar(DD.DRILLS[key].count_sql(), d=today_d)

    active = await tile_value("active_loads")
    unconfirmed = await tile_value("unconfirmed_brokered")
    thin_margin = await tile_value("thin_margin")
    in_transit = await tile_value("in_transit")
    exceptions = await tile_value("exceptions")
    awaiting_pod = await tile_value("delivered_no_pod")

    open_ar = await tile_value("open_ar")
    overdue_ar = await tile_value("overdue_ar")
    carrier_due = await tile_value("carrier_pay_due")
    payroll_due = await tile_value("payroll_obligation")
    unbilled = await tile_value("unbilled_delivered")

    # ---- compliance ------------------------------------------------------
    soon = today_d + timedelta(days=30)
    binds = {"o": org, "d": today_d, "soon": soon}
    # Has a REAL FMCSA lookup landed on this org's carriers recently? Seeded
    # authority carries source 'SEED' and cannot satisfy this.
    fmcsa_live_carriers = await scalar("""
        SELECT count(*) FROM public.trucking_carriers
        WHERE org_id = :o AND authority_source = 'FMCSA_LIVE'
          AND authority_checked_at IS NOT NULL
          AND authority_checked_at > now() - interval '30 days'""")

    expiring = (await db.execute(
        text(DD.DRILLS["expiring_credentials"].rows_sql(200)), binds)).mappings().all()
    carrier_issues = (await db.execute(
        text(DD.DRILLS["carrier_issues"].rows_sql(200)), binds)).mappings().all()

    # ---- margin, and only where it can be substantiated ------------------
    margin_rows = (await db.execute(text("""
        SELECT l.load_number, i.linehaul_cents, i.accessorial_cents,
               COALESCE(SUM(c.amount_cents), 0) AS cost,
               MIN(CASE c.authority
                     WHEN 'MODELED' THEN 0 WHEN 'PLATFORM_REPORTED' THEN 1
                     WHEN 'CORROBORATED' THEN 2 ELSE 3 END) AS weakest
        FROM public.trucking_loads l
        JOIN public.trucking_invoices i
          ON i.load_id = l.id AND i.org_id = l.org_id
        LEFT JOIN public.trucking_load_costs c
          ON c.load_id = l.id AND c.org_id = l.org_id
        WHERE l.org_id = :o
        GROUP BY l.load_number, i.linehaul_cents, i.accessorial_cents
        ORDER BY l.load_number"""), {"o": org})).all()

    AUTH = ["MODELED", "PLATFORM_REPORTED", "CORROBORATED", "FINANCIAL_ACTUAL"]
    margins: List[dict] = []
    below_floor = 0
    for load_number, lh, acc, cost, weakest in margin_rows:
        revenue = int(lh or 0) + int(acc or 0)
        cm = revenue - int(cost or 0)
        pct = round(100.0 * cm / revenue, 2) if revenue else None
        if pct is not None and pct < 15.0:
            below_floor += 1
        margins.append({
            "load_number": load_number, "revenue_cents": revenue,
            "cost_cents": int(cost or 0), "contribution_margin_cents": cm,
            "margin_pct": pct,
            "authority": AUTH[weakest] if weakest is not None else "MODELED",
        })

    # ---- hiring ----------------------------------------------------------
    interviewed = await tile_value("interviews_completed")
    needs_review = await tile_value("needs_recruiter_review")

    return {
        "as_of": today_d.isoformat(),
        "operations": [
            _tile("Active loads", active, authority="OPERATING_TRUTH",
                  drill="active_loads",
                  hint="what is moving or waiting to move"),
            _tile("In transit", in_transit, authority="OPERATING_TRUTH",
                  drill="in_transit"),
            _tile("Exceptions", exceptions, authority="OPERATING_TRUTH",
                  drill="exceptions",
                  tone="warn" if exceptions else "neutral"),
            _tile("Brokered, no agreed rate", unconfirmed,
                  authority="OPERATING_TRUTH",
                  drill="unconfirmed_brokered",
                  hint=("these will not dispatch. A brokered load without an "
                        "accepted rate confirmation has no document its "
                        "carrier payable could be defended against."),
                  tone="warn" if unconfirmed else "neutral"),
            _tile("Delivered, no POD", awaiting_pod, authority="OPERATING_TRUTH",
                  drill="delivered_no_pod",
                  hint=("these cannot be invoiced. A driver marking a load "
                        "delivered is not proof of delivery."),
                  tone="warn" if awaiting_pod else "neutral"),
            # MARGIN, ON THE BOARD. Every other question an operator has --
            # what is moving, what is stuck, who owes us -- was one click from
            # this screen, and "which of these did we barely make anything on"
            # was not on it at all. The load page has always carried the
            # number; you had to already suspect a load to go and look.
            #
            # MODELED on purpose, and graded as such: it divides revenue by the
            # costs recorded against each load, whose authorities differ, so it
            # is only as good as its weakest cost. A prompt to open the load,
            # not a measured result.
            _tile("Loads at or under %g%% margin" % DD.THIN_MARGIN_PCT,
                  thin_margin, authority="MODELED",
                  drill="thin_margin",
                  hint=("modeled from the costs recorded against each load. "
                        "Open one to see which cost holds the grade down, and "
                        "whether the rate, the accessorials or the carrier pay "
                        "is the thing to change."),
                  tone="warn" if thin_margin else "neutral"),
        ],
        "money": [
            _tile("Open AR", open_ar, authority="INVOICED",
                  drill="open_ar",
                  hint="invoiced and unpaid — not cash"),
            _tile("Overdue AR", overdue_ar, authority="INVOICED",
                  drill="overdue_ar",
                  tone="warn" if overdue_ar else "neutral"),
            _tile("Unbilled delivered", unbilled, authority="OPERATING_TRUTH",
                  drill="unbilled_delivered",
                  hint="earned, not yet invoiced. Not revenue and not AR."),
            _tile("Carrier pay due", carrier_due, authority="APPROVED_PAYABLE",
                  drill="carrier_pay_due"),
            _tile("Payroll obligation", payroll_due, authority="PAYROLL_INPUT",
                  drill="payroll_obligation",
                  hint=("W-2 driver earnings routed to payroll. Withholding "
                        "and employer contributions are additional.")),
        ],
        "working_capital": {
            "note": ("A broker often pays the carrier before the shipper pays "
                     "them. The gap below is that exposure. It is MODELED from "
                     "terms, not a cash forecast from a bank feed."),
            "authority": "MODELED",
            "receivable_cents": open_ar,
            "payable_cents": carrier_due + payroll_due,
            "gap_cents": (carrier_due + payroll_due) - open_ar,
            "bank_connected": False,
        },
        "margin": {
            "basis": "MODELED",
            "realised_note": (
                "These are MODELED contribution margins. A realised margin "
                "needs cash collected AND costs with FINANCIAL_ACTUAL "
                "authority; /loads/{id}/margin reports both and the variance."),
            "loads": margins,
            "below_floor_count": below_floor,
            # The same constant the Today tile and its drill use, so the board
            # cannot show two floors.
            "floor_pct": DD.MARGIN_FLOOR_PCT,
            "note": ("Contribution margin: revenue less direct costs. Not "
                     "profit. Each row is graded by its WEAKEST cost "
                     "authority."),
        },
        "compliance": {
            "expiring_credentials": [
                # `full_name` was read straight off the drill's row, and the
                # drill has never selected it -- nor does any reachable table
                # have such a column. It could not have worked. It never threw
                # because the drill had never returned a ROW: no credential in
                # the demo data was expiring, the comprehension ran zero times,
                # and the board looked healthy. Seeding one expired card turned
                # the flagship screen into a 500.
                #
                # A dispatcher identifies a driver by their code anyway, so the
                # name is optional and read defensively: this line must not be
                # able to take the board down again.
                {"driver": r["driver_code"],
                 "driver_name": r.get("full_name"),
                 "credential": r["credential_type"],
                 "expires_on": (r["expires_on"].isoformat()
                                if r["expires_on"] else None),
                 "days": ((r["expires_on"] - today_d).days
                          if r["expires_on"] else None)}
                for r in expiring],
            "expiring_credentials_drill": "/api/trucking/drill/expiring_credentials",
            "carrier_issues": [
                {"carrier": r["name"], "authority_status": r["authority_status"],
                 "authority_source": r["authority_source"],
                 "insurance_expires_on": (r["insurance_expires_on"].isoformat()
                                          if r["insurance_expires_on"] else None)}
                for r in carrier_issues],
            "carrier_issues_drill": "/api/trucking/drill/carrier_issues",
            # FMCSA IS NO LONGER ON THIS LIST BY DEFAULT.
            # It was hard-coded as not connected while `fmcsa_authority` was
            # making real requests to the live operating-status dataset. A
            # disclosure that is wrong in the CAUTIOUS direction still teaches
            # a buyer not to trust the disclosures.
            "not_connected": _unconnected_compliance_systems(
                fmcsa_evidenced=bool(fmcsa_live_carriers)),
            "fmcsa_live_carriers": fmcsa_live_carriers,
        },
        "people": {
            "interviews_completed": interviewed,
            "interviews_completed_drill": "/api/trucking/drill/interviews_completed",
            "needs_recruiter_review": needs_review,
            "needs_recruiter_review_drill": "/api/trucking/drill/needs_recruiter_review",
            "note": ("An interview marked INCOMPLETE or INSUFFICIENT_EVIDENCE "
                     "is not a rejection. It means the interview did not "
                     "establish enough, and a human should look."),
        },
        "disclosure": {
            "not_connected": ["bank settlement", "GL posting", "telematics",
                              "ELD / hours of service", "FMCSA live lookup"],
            "note": ("Figures above are derived from this database. Nothing "
                     "here is corroborated by a bank, a GL or a government "
                     "system, and no tile claims otherwise."),
        },
    }


# ---------------------------------------------------------------------------
# Rate confirmations
# ---------------------------------------------------------------------------

def _ratecon_row(r) -> dict:
    return {
        "id": str(r["id"]),
        "confirmation_number": r["confirmation_number"],
        "state": r["state"],
        "carrier_id": str(r["carrier_id"]),
        "linehaul_cents": int(r["linehaul_cents"] or 0),
        "fuel_surcharge_cents": int(r["fuel_surcharge_cents"] or 0),
        "agreed_total_cents": int(r["agreed_total_cents"] or 0),
        "approved_accessorials": r["approved_accessorials"] or [],
        "issued_at": r["issued_at"].isoformat() if r["issued_at"] else None,
        "accepted_at": r["accepted_at"].isoformat() if r["accepted_at"] else None,
        "accepted_by": r["accepted_by"],
        "accepted_channel": r["accepted_channel"],
        "document_sha256": r["document_sha256"],
        "supersedes_id": str(r["supersedes_id"]) if r["supersedes_id"] else None,
        "amendment_reason": r["amendment_reason"],
    }


async def _load_for(db, org, load_id):
    row = (await db.execute(text("""
        SELECT id, load_number, org_id, fulfilment_mode, carrier_id, status,
               carrier_rate_cents, customer_rate_cents, rate_confirmation_id,
               origin_city, origin_state, destination_city, destination_state,
               equipment_required, commodity
        FROM public.trucking_loads
        WHERE org_id = :o AND id = :l"""),
        {"o": org, "l": load_id})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404,
                            detail="no such load for this organisation")
    return row


@router.get("/loads/{load_id}")
async def load_detail(load_id: UUID, actor: Actor = Depends(require_org),
                      db: AsyncSession = Depends(db_session)) -> dict:
    """One load, and everything that decides what it is worth.

    THE WHOLE CHAIN ON ONE RESPONSE, WITH ITS AUTHORITY ATTACHED
    A load's story is a sequence of facts of different kinds: the shipper's
    contract rate is a commitment, the carrier's rate is an agreement, the
    tracking is the carrier telling us where they are, the POD is a document,
    and the margin is arithmetic over all of it. Rendering them as one flat
    list of fields teaches an operator that they are the same kind of thing.

    So each block below carries what it is and how strong it is, and the
    refusals -- why this cannot be invoiced, why it cannot be dispatched --
    are part of the response rather than something the UI has to infer from
    which fields are null.
    """
    _require_ops(actor)
    org = actor.org_id
    load = await _load_for(db, org, load_id)

    full = (await db.execute(text("""
        SELECT l.*, c.name AS customer_name, c.payment_terms_days,
               car.name AS carrier_name, car.authority_status,
               car.authority_source, car.authority_checked_at,
               car.insurance_expires_on, car.is_approved,
               d.driver_code, d.worker_classification
        FROM public.trucking_loads l
        JOIN public.trucking_customers c
          ON c.id = l.customer_id AND c.org_id = l.org_id
        LEFT JOIN public.trucking_carriers car
          ON car.id = l.carrier_id AND car.org_id = l.org_id
        LEFT JOIN public.trucking_drivers d
          ON d.id = l.driver_id AND d.org_id = l.org_id
        WHERE l.org_id = :o AND l.id = :l"""),
        {"o": org, "l": load_id})).mappings().first()

    events = (await db.execute(text("""
        SELECT event_type, occurred_at, source, note
        FROM public.trucking_load_events
        WHERE org_id = :o AND load_id = :l
        ORDER BY occurred_at"""), {"o": org, "l": load_id})).mappings().all()

    accessorials = (await db.execute(text("""
        SELECT id, accessorial_type, direction, state, measured_quantity,
               measured_unit, free_allowance, billable_quantity, rate_cents,
               amount_cents, approved_by, approved_at, rate_rule_ref
        FROM public.trucking_accessorials
        WHERE org_id = :o AND load_id = :l
        ORDER BY created_at"""), {"o": org, "l": load_id})).mappings().all()

    costs = (await db.execute(text("""
        SELECT cost_type, amount_cents, authority, note
        FROM public.trucking_load_costs
        WHERE org_id = :o AND load_id = :l
        ORDER BY amount_cents DESC"""),
        {"o": org, "l": load_id})).mappings().all()

    pod = (await db.execute(text("""
        SELECT id, received_at, receiver_name, signature_kind,
               evidence_strength, exceptions_noted, document_sha256
        FROM public.proof_of_delivery
        WHERE org_id = :o AND load_id = :l"""),
        {"o": org, "l": load_id})).mappings().first()

    invoice = (await db.execute(text("""
        SELECT id, invoice_number, state, issued_on, due_on, linehaul_cents,
               accessorial_cents, total_cents, paid_cents, derivation_note
        FROM public.trucking_invoices
        WHERE org_id = :o AND load_id = :l"""),
        {"o": org, "l": load_id})).mappings().first()

    settlements = (await db.execute(text("""
        SELECT id, payee_kind, state, linehaul_cents, accessorial_cents,
               deduction_cents, total_cents, derivation_note,
               rate_confirmation_id
        FROM public.trucking_settlements
        WHERE org_id = :o AND load_id = :l
        ORDER BY created_at"""), {"o": org, "l": load_id})).mappings().all()

    ratecons = (await db.execute(text("""
        SELECT * FROM public.trucking_rate_confirmations
        WHERE org_id = :o AND load_id = :l
        ORDER BY created_at"""), {"o": org, "l": load_id})).mappings().all()
    live_rc = next((r for r in ratecons
                    if r["state"] in (RC.DRAFT, RC.ISSUED, RC.ACCEPTED)), None)

    dispatch = RC.check_dispatch(
        load=type("L", (), dict(full))(),
        ratecon=type("R", (), dict(live_rc))() if live_rc else None)

    # WHY THIS CANNOT BE INVOICED, said out loud.
    billing_block = None
    if invoice is None:
        try:
            B.build_invoice(
                load=type("L", (), dict(full))(),
                pod=type("P", (), dict(pod))() if pod else
                    type("P", (), {"evidence_strength": None})(),
                accessorials=[type("A", (), dict(a))() for a in accessorials])
        except B.BillingRefused as exc:
            billing_block = {"code": exc.code, "detail": exc.detail}

    margin = None
    if invoice is not None:
        cost_objs = [type("C", (), dict(c))() for c in costs]
        inv_obj = type("I", (), dict(invoice))()
        pair = B.margin_pair(invoice=inv_obj, costs=cost_objs)
        margin = {
            "modeled": pair.modeled.as_dict(),
            "realised_state": pair.realised_state,
            "realised_margin_cents": pair.realised_margin_cents,
            "variance_cents": pair.variance_cents,
            "note": pair.note,
        }

    return {
        "load": _jsonable(dict(full)),
        "customer": {"name": full["customer_name"],
                     "payment_terms_days": full["payment_terms_days"]},
        "carrier": ({"name": full["carrier_name"],
                     "authority_status": full["authority_status"],
                     "authority_source": full["authority_source"],
                     "authority_checked_at": (
                         full["authority_checked_at"].isoformat()
                         if full["authority_checked_at"] else None),
                     "insurance_expires_on": (
                         full["insurance_expires_on"].isoformat()
                         if full["insurance_expires_on"] else None)}
                    if full["carrier_name"] else None),
        "driver": ({"driver_code": full["driver_code"],
                    "worker_classification": full["worker_classification"]}
                   if full["driver_code"] else None),
        "rate_confirmation": _ratecon_row(live_rc) if live_rc else None,
        "rate_confirmation_history": [_ratecon_row(r) for r in ratecons],
        "dispatch": {"allowed": dispatch.allowed,
                     "refusal_codes": dispatch.refusal_codes,
                     "reasons": dispatch.reasons},
        "events": [_jsonable(dict(e)) for e in events],
        "accessorials": [_jsonable(dict(a)) for a in accessorials],
        "proof_of_delivery": _jsonable(dict(pod)) if pod else None,
        "invoice": _jsonable(dict(invoice)) if invoice else None,
        "billing_blocked_by": billing_block,
        "settlements": [_jsonable(dict(x)) for x in settlements],
        "costs": [_jsonable(dict(c)) for c in costs],
        "margin": margin,
        "disclosure": {
            "tracking_authority": (
                "Load events carry the source that reported them. Nothing here "
                "comes from an ELD or a telematics feed; CARRIER_REPORTED is "
                "the carrier telling us where they are."),
            "not_connected": _unconnected_compliance_systems(
                fmcsa_evidenced=(full["authority_source"] == "FMCSA_LIVE")),
        },
    }


@router.get("/loads/{load_id}/rate-confirmation")
async def get_rate_confirmation(load_id: UUID,
                                actor: Actor = Depends(require_org),
                                db: AsyncSession = Depends(db_session)) -> dict:
    """The confirmation governing this load, and whether it may dispatch.

    Returns the whole chain, superseded documents included. A settlement may
    cite an earlier one, and hiding it would make that settlement look
    unsupported.
    """
    _require_ops(actor)
    load = await _load_for(db, actor.org_id, load_id)

    rows = (await db.execute(text("""
        SELECT * FROM public.trucking_rate_confirmations
        WHERE org_id = :o AND load_id = :l
        ORDER BY created_at"""),
        {"o": actor.org_id, "l": load_id})).mappings().all()

    live = next((r for r in rows if r["state"] in
                 (RC.DRAFT, RC.ISSUED, RC.ACCEPTED)), None)
    live_obj = None
    if live is not None:
        live_obj = type("R", (), dict(live))()

    decision = RC.check_dispatch(
        load=type("L", (), dict(load))(), ratecon=live_obj)

    return {
        "load_id": str(load_id),
        "load_number": load["load_number"],
        "fulfilment_mode": load["fulfilment_mode"],
        "current": _ratecon_row(live) if live is not None else None,
        "history": [_ratecon_row(r) for r in rows],
        "dispatch": {
            "allowed": decision.allowed,
            "refusal_codes": decision.refusal_codes,
            "reasons": decision.reasons,
        },
        "note": ("A rate confirmation establishes what was agreed. It does "
                 "not establish that the carrier may haul -- authority and "
                 "insurance are checked separately and both apply."),
    }


@router.post("/loads/{load_id}/rate-confirmation")
async def issue_rate_confirmation(
        load_id: UUID,
        payload: Dict[str, Any],
        actor: Actor = Depends(require_org),
        db: AsyncSession = Depends(db_session)) -> dict:
    """Issue a confirmation for this load.

    The document is rendered here and its hash stored, so what the carrier is
    sent and what we can later verify are the same bytes.
    """
    _require_ops(actor)
    load = await _load_for(db, actor.org_id, load_id)

    if (load["fulfilment_mode"] or "").upper() != "BROKERED":
        raise HTTPException(
            status_code=409,
            detail=("only a brokered load has a carrier to agree a rate with. "
                    "An own-fleet load is gated by driver eligibility."))

    carrier_id = payload.get("carrier_id") or load["carrier_id"]
    if not carrier_id:
        raise HTTPException(status_code=409,
                            detail="this load has no carrier assigned")

    carrier = (await db.execute(text("""
        SELECT id, name FROM public.trucking_carriers
        WHERE org_id = :o AND id = :c"""),
        {"o": actor.org_id, "c": carrier_id})).mappings().first()
    if carrier is None:
        raise HTTPException(status_code=404,
                            detail="no such carrier for this organisation")

    existing = (await db.execute(text("""
        SELECT id, state FROM public.trucking_rate_confirmations
        WHERE org_id = :o AND load_id = :l
          AND state IN ('DRAFT','ISSUED','ACCEPTED')"""),
        {"o": actor.org_id, "l": load_id})).mappings().first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(f"this load already has a {existing['state']} rate "
                    f"confirmation. Amend it rather than issuing a second one: "
                    f"two live rates for one load means the settlement picks "
                    f"one, and which one it picks is not a decision anybody "
                    f"made."))

    try:
        linehaul = int(payload.get("linehaul_cents") or 0)
        fsc = int(payload.get("fuel_surcharge_cents") or 0)
        terms = RC.parse_terms(payload.get("approved_accessorials"))
    except RC.RateConRefused as exc:
        raise HTTPException(status_code=422,
                            detail={"code": exc.code, "detail": exc.detail})
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if linehaul < 0 or fsc < 0:
        raise HTTPException(status_code=422,
                            detail="a rate confirmation is not a credit memo")

    number = (payload.get("confirmation_number")
              or f"RC-{load['load_number']}")
    document = RC.render_document(
        confirmation_number=number, carrier_name=carrier["name"],
        load_number=load["load_number"],
        origin=f"{load['origin_city']} {load['origin_state']}",
        destination=f"{load['destination_city']} {load['destination_state']}",
        linehaul_cents=linehaul, fuel_surcharge_cents=fsc, terms=terms,
        equipment=load["equipment_required"] or "",
        commodity=load["commodity"] or "")

    rc_id = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_rate_confirmations
        (id,org_id,load_id,carrier_id,confirmation_number,linehaul_cents,
         fuel_surcharge_cents,agreed_total_cents,approved_accessorials,
         state,issued_at,document_sha256)
        VALUES (:i,:o,:l,:c,:num,:lh,:fsc,:tot,CAST(:terms AS jsonb),
                'ISSUED',now(),:sha)"""),
        {"i": rc_id, "o": actor.org_id, "l": load_id, "c": carrier_id,
         "num": number, "lh": linehaul, "fsc": fsc, "tot": linehaul + fsc,
         "terms": json.dumps([t.as_dict() for t in terms]),
         "sha": RC.document_hash(document)})
    await db.execute(text("""UPDATE public.trucking_loads
        SET rate_confirmation_id = :rc WHERE org_id = :o AND id = :l"""),
        {"rc": rc_id, "o": actor.org_id, "l": load_id})
    await db.commit()

    return {"id": str(rc_id), "confirmation_number": number,
            "state": "ISSUED", "document": document,
            "document_sha256": RC.document_hash(document),
            "note": ("Issued, not agreed. The load will not dispatch until "
                     "the carrier accepts this.")}


@router.post("/rate-confirmations/{ratecon_id}/accept")
async def accept_rate_confirmation(
        ratecon_id: UUID,
        payload: Dict[str, Any],
        actor: Actor = Depends(require_org),
        db: AsyncSession = Depends(db_session)) -> dict:
    """Record that the carrier agreed.

    ACCEPTED is the state that authorises a payable, so it carries who agreed
    and through what channel. The database refuses the row without them.
    """
    _require_ops(actor)
    row = (await db.execute(text("""
        SELECT * FROM public.trucking_rate_confirmations
        WHERE org_id = :o AND id = :i"""),
        {"o": actor.org_id, "i": ratecon_id})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404,
                            detail="no such rate confirmation")

    accepted_by = (payload.get("accepted_by") or "").strip()
    if not accepted_by:
        raise HTTPException(
            status_code=422,
            detail=("record who accepted it. A confirmation that authorises a "
                    "payable with no counterparty named is the field it was "
                    "meant to replace."))

    try:
        RC.validate_transition(row["state"], RC.ACCEPTED)
    except RC.RateConRefused as exc:
        raise HTTPException(status_code=409,
                            detail={"code": exc.code, "detail": exc.detail})

    await db.execute(text("""UPDATE public.trucking_rate_confirmations
        SET state='ACCEPTED', accepted_at=now(), accepted_by=:by,
            accepted_channel=:ch
        WHERE org_id=:o AND id=:i"""),
        {"o": actor.org_id, "i": ratecon_id, "by": accepted_by,
         "ch": (payload.get("channel") or "UNRECORDED")[:40]})
    await db.commit()
    return {"id": str(ratecon_id), "state": "ACCEPTED",
            "accepted_by": accepted_by,
            "note": "This load may now be dispatched to this carrier."}


@router.post("/rate-confirmations/{ratecon_id}/amend")
async def amend_rate_confirmation(
        ratecon_id: UUID,
        payload: Dict[str, Any],
        actor: Actor = Depends(require_org),
        db: AsyncSession = Depends(db_session)) -> dict:
    """Supersede an accepted confirmation with new terms.

    The original is kept and marked SUPERSEDED, because a settlement already
    citing it still has to be defensible.
    """
    _require_ops(actor)
    row = (await db.execute(text("""
        SELECT * FROM public.trucking_rate_confirmations
        WHERE org_id = :o AND id = :i"""),
        {"o": actor.org_id, "i": ratecon_id})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404,
                            detail="no such rate confirmation")

    reason = (payload.get("reason") or "").strip()
    try:
        RC.validate_amendment(original_state=row["state"], reason=reason)
        RC.validate_transition(row["state"], RC.SUPERSEDED)
        terms = RC.parse_terms(
            payload.get("approved_accessorials")
            if "approved_accessorials" in payload
            else row["approved_accessorials"])
    except RC.RateConRefused as exc:
        raise HTTPException(status_code=409,
                            detail={"code": exc.code, "detail": exc.detail})

    load = await _load_for(db, actor.org_id, row["load_id"])
    carrier = (await db.execute(text(
        "SELECT name FROM public.trucking_carriers WHERE id = :c"),
        {"c": row["carrier_id"]})).mappings().first()

    linehaul = int(payload.get("linehaul_cents", row["linehaul_cents"]) or 0)
    fsc = int(payload.get("fuel_surcharge_cents",
                          row["fuel_surcharge_cents"]) or 0)
    number = f"{row['confirmation_number']}-A"
    document = RC.render_document(
        confirmation_number=number,
        carrier_name=(carrier or {}).get("name", "the carrier"),
        load_number=load["load_number"],
        origin=f"{load['origin_city']} {load['origin_state']}",
        destination=f"{load['destination_city']} {load['destination_state']}",
        linehaul_cents=linehaul, fuel_surcharge_cents=fsc, terms=terms,
        equipment=load["equipment_required"] or "",
        commodity=load["commodity"] or "")

    await db.execute(text("""UPDATE public.trucking_rate_confirmations
        SET state='SUPERSEDED', superseded_at=now()
        WHERE org_id=:o AND id=:i"""),
        {"o": actor.org_id, "i": ratecon_id})

    new_id = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_rate_confirmations
        (id,org_id,load_id,carrier_id,confirmation_number,linehaul_cents,
         fuel_surcharge_cents,agreed_total_cents,approved_accessorials,
         state,issued_at,document_sha256,supersedes_id,amendment_reason)
        VALUES (:i,:o,:l,:c,:num,:lh,:fsc,:tot,CAST(:terms AS jsonb),
                'ISSUED',now(),:sha,:sup,:reason)"""),
        {"i": new_id, "o": actor.org_id, "l": row["load_id"],
         "c": row["carrier_id"], "num": number, "lh": linehaul, "fsc": fsc,
         "tot": linehaul + fsc,
         "terms": json.dumps([t.as_dict() for t in terms]),
         "sha": RC.document_hash(document), "sup": ratecon_id,
         "reason": reason})
    await db.execute(text("""UPDATE public.trucking_loads
        SET rate_confirmation_id = :rc WHERE org_id = :o AND id = :l"""),
        {"rc": new_id, "o": actor.org_id, "l": row["load_id"]})
    await db.commit()

    return {"id": str(new_id), "supersedes": str(ratecon_id),
            "confirmation_number": number, "state": "ISSUED",
            "document": document, "reason": reason,
            "note": ("The original is kept and marked SUPERSEDED. The load "
                     "cannot dispatch again until this amendment is "
                     "accepted.")}


@router.get("/loads/{load_id}/margin")
async def load_margin(load_id: UUID, actor: Actor = Depends(require_org),
                      db: AsyncSession = Depends(db_session)) -> dict:
    """One load's economics, with every cost's authority."""
    _require_ops(actor)

    inv = (await db.execute(text("""
        SELECT linehaul_cents, accessorial_cents, total_cents,
               derivation_note, paid_cents
        FROM public.trucking_invoices WHERE org_id=:o AND load_id=:l"""),
        {"o": actor.org_id, "l": load_id})).first()
    if inv is None:
        raise HTTPException(
            status_code=409,
            detail=("this load has not been invoiced, so there is revenue to "
                    "estimate but none to report"))

    costs = (await db.execute(text("""
        SELECT cost_type, amount_cents, authority, source_ref
        FROM public.trucking_load_costs WHERE org_id=:o AND load_id=:l"""),
        {"o": actor.org_id, "l": load_id})).all()

    inv_obj = type("I", (), {"linehaul_cents": inv[0],
                             "accessorial_cents": inv[1],
                             "paid_cents": int(inv[4] or 0)})()
    cost_objs = [type("C", (), {"cost_type": c[0], "amount_cents": c[1],
                                "authority": c[2]})() for c in costs]
    # BOTH margins. Showing one and calling it "margin" is the overclaim this
    # avoids: the modelled figure is what we expect to have made; the realised
    # one counts only cash collected against costs that were actually paid.
    paid = int(inv[4] or 0)
    pair = B.margin_pair(invoice=inv_obj, costs=cost_objs,
                         cash_collected_cents=paid)

    return {**pair.as_dict(),
            "invoice_derivation": inv[3],
            "costs": [{"type": c[0], "amount_cents": c[1],
                       "authority": c[2], "source_ref": c[3]} for c in costs]}


@router.get("/drivers/{driver_id}/eligibility")
async def driver_eligibility(driver_id: UUID, equipment: str = "DRY_VAN",
                             hazmat: bool = False,
                             actor: Actor = Depends(require_org),
                             db: AsyncSession = Depends(db_session)) -> dict:
    """Can this driver take this kind of freight, and if not, exactly why."""
    _require_ops(actor)

    drv = (await db.execute(text("""
        SELECT status, worker_classification FROM public.trucking_drivers
        WHERE org_id=:o AND id=:d"""),
        {"o": actor.org_id, "d": driver_id})).first()
    if drv is None:
        raise HTTPException(status_code=404, detail="Driver not found")

    creds = (await db.execute(text("""
        SELECT credential_type, expires_on, verification_state
        FROM public.driver_credentials WHERE org_id=:o AND driver_id=:d"""),
        {"o": actor.org_id, "d": driver_id})).all()

    driver_obj = type("D", (), {"status": drv[0],
                                "worker_classification": drv[1]})()
    cred_objs = [type("C", (), {"credential_type": c[0], "expires_on": c[1],
                                "verification_state": c[2]})() for c in creds]

    decision = EL.check_driver(driver=driver_obj, credentials=cred_objs,
                               equipment=equipment, hazmat=hazmat)
    return decision.as_dict()


@router.get("/fmcsa/connectivity")
async def fmcsa_connectivity(actor: Actor = Depends(require_org)) -> dict:
    """What carrier-authority evidence this deployment can actually obtain."""
    _require_ops(actor)
    return FMCSA.connectivity()


@router.post("/carriers/{carrier_id}/refresh-authority")
async def refresh_authority(carrier_id: UUID,
                            actor: Actor = Depends(require_org),
                            db: AsyncSession = Depends(db_session)) -> dict:
    """Check this carrier against FMCSA now, and record what came back.

    This is what a dispatcher does about the "authority last checked 214 days
    ago" alert on the Today board. A FAILED lookup deliberately does not touch
    authority_checked_at -- otherwise a run of failures would keep the carrier
    looking freshly verified while nothing had been checked, which is exactly
    the state the staleness rule exists to catch.
    """
    _require_ops(actor)
    try:
        out = await FMCSA.refresh_carrier(db, org_id=actor.org_id,
                                          carrier_id=carrier_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await db.commit()
    return out


@router.get("/carriers/{carrier_id}/eligibility")
async def carrier_eligibility(carrier_id: UUID,
                              actor: Actor = Depends(require_org),
                              db: AsyncSession = Depends(db_session)) -> dict:
    """May this carrier be dispatched, and if not, exactly why."""
    _require_ops(actor)
    row = (await db.execute(text("""
        SELECT name, is_approved, authority_status, authority_source,
               authority_checked_at, insurance_expires_on
        FROM public.trucking_carriers WHERE org_id=:o AND id=:c"""),
        {"o": actor.org_id, "c": carrier_id})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Carrier not found")

    carrier = type("C", (), {
        "is_approved": row[1], "authority_status": row[2],
        "authority_source": row[3], "authority_checked_at": row[4],
        "insurance_expires_on": row[5]})()
    decision = EL.check_carrier(carrier=carrier)
    return {"carrier": row[0], **decision.as_dict()}


# ---------------------------------------------------------------------------
# Proof of delivery
# ---------------------------------------------------------------------------

@router.post("/loads/{load_id}/pod")
async def upload_pod(load_id: UUID,
                     file: UploadFile = File(...),
                     receiver_name: str = Form(""),
                     evidence_strength: str = Form("SIGNED_DOCUMENT"),
                     signature_kind: str = Form("SCANNED_DOCUMENT"),
                     actor: Actor = Depends(require_org),
                     db: AsyncSession = Depends(db_session)) -> dict:
    """Attach the signed document, and bind it to this load by hash.

    Billing already refuses to invoice without a POD of sufficient strength.
    This gives that POD an artifact a disputing customer can be shown.
    """
    _require_ops(actor)
    if not isinstance(receiver_name, str):
        receiver_name = ""
    if not isinstance(evidence_strength, str):
        evidence_strength = "SIGNED_DOCUMENT"
    if not isinstance(signature_kind, str):
        signature_kind = "SCANNED_DOCUMENT"

    load = (await db.execute(text("""
        SELECT org_id, status, pod_id FROM public.trucking_loads
        WHERE org_id = :o AND id = :l"""),
        {"o": actor.org_id, "l": load_id})).first()
    if load is None:
        raise HTTPException(status_code=404, detail="Load not found")

    existing_sha = None
    if load[2]:
        existing_sha = (await db.execute(text(
            "SELECT document_sha256 FROM public.proof_of_delivery WHERE id=:i"),
            {"i": load[2]})).scalar_one_or_none()

    data = await file.read()
    try:
        doc = POD.store_document(org_id=actor.org_id, load_id=load_id,
                                 data=data,
                                 mime_type=file.content_type or "application/pdf")
        POD.validate_binding(load_org_id=load[0], actor_org_id=actor.org_id,
                             load_status=load[1], existing_sha=existing_sha,
                             new_sha=doc.sha256,
                             evidence_strength=evidence_strength)
    except POD.PodRefused as exc:
        status = 409 if exc.code in ("POD_ALREADY_BOUND", "WRONG_TENANT") else 422
        raise HTTPException(status_code=status,
                            detail={"code": exc.code, "detail": exc.detail})

    if load[2] and existing_sha == doc.sha256:
        pod_id = load[2]
    else:
        pod_id = uuid.uuid4()
        await db.execute(text("""
            INSERT INTO public.proof_of_delivery
                (id, org_id, load_id, received_at, receiver_name,
                 signature_kind, document_ref, document_sha256,
                 evidence_strength)
            VALUES (:i,:o,:l, now(), :r, :sk, :ref, :sha, :es)"""),
            {"i": pod_id, "o": actor.org_id, "l": load_id,
             "r": receiver_name or None, "sk": signature_kind,
             "ref": doc.storage_ref, "sha": doc.sha256,
             "es": evidence_strength})
        await db.execute(text("""
            UPDATE public.trucking_loads
            SET pod_id = :p, status = 'POD_RECEIVED'
            WHERE id = :l AND org_id = :o"""),
            {"p": pod_id, "l": load_id, "o": actor.org_id})
    await db.commit()

    return {"pod_id": str(pod_id), "sha256": doc.sha256,
            "byte_size": doc.byte_size, "evidence_strength": evidence_strength,
            "billable": evidence_strength in
                        ("RECEIVER_ACKNOWLEDGED", "SIGNED_DOCUMENT",
                         "EDI_CONFIRMED"),
            "note": ("This records that a document with this hash was bound "
                     "to this load. It does not verify the signature.")}


@router.get("/loads/{load_id}/pod/integrity")
async def pod_integrity(load_id: UUID, actor: Actor = Depends(require_org),
                        db: AsyncSession = Depends(db_session)) -> dict:
    """Is the document still the one we accepted?

    An invoice may cite this POD months later. "The file on disk today" and
    "the file we approved" are different claims unless something re-reads it.
    """
    _require_ops(actor)
    row = (await db.execute(text("""
        SELECT p.document_ref, p.document_sha256, p.evidence_strength,
               p.received_at, p.receiver_name
        FROM public.proof_of_delivery p
        WHERE p.org_id = :o AND p.load_id = :l"""),
        {"o": actor.org_id, "l": load_id})).first()
    if row is None:
        raise HTTPException(status_code=404,
                            detail="this load has no proof of delivery")
    if not row[0]:
        return {"has_document": False,
                "evidence_strength": row[2],
                "note": ("a POD is recorded but no document was uploaded. The "
                         "evidence is the record, not an artifact.")}

    r = POD.verify_document(storage_ref=row[0], recorded_sha256=row[1],
                            org_id=actor.org_id)
    return {"has_document": True, "intact": r.intact, "code": r.code,
            "detail": r.detail, "recorded_sha256": r.recorded_sha256,
            "actual_sha256": r.actual_sha256,
            "evidence_strength": row[2],
            "received_at": row[3].isoformat() if row[3] else None,
            "receiver_name": row[4]}


@router.get("/loads/{load_id}/pod/document")
async def pod_document(load_id: UUID, actor: Actor = Depends(require_org),
                       db: AsyncSession = Depends(db_session)):
    """Show the document itself."""
    _require_ops(actor)
    row = (await db.execute(text("""
        SELECT document_ref FROM public.proof_of_delivery
        WHERE org_id = :o AND load_id = :l"""),
        {"o": actor.org_id, "l": load_id})).first()
    if row is None or not row[0]:
        raise HTTPException(status_code=404, detail="No POD document")
    try:
        data = POD.read_document(row[0], org_id=actor.org_id)
    except POD.PodRefused as exc:
        raise HTTPException(status_code=404,
                            detail={"code": exc.code, "detail": exc.detail})
    ext = row[0].rsplit(".", 1)[-1].lower()
    mime = {"pdf": "application/pdf", "jpg": "image/jpeg",
            "png": "image/png"}.get(ext, "application/octet-stream")
    return Response(content=data, media_type=mime)
