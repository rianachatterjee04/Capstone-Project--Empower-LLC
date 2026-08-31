#!/usr/bin/env python3
"""The brokered flow, end to end, with every refusal on the way.

    carrier sourcing -> rate confirmation -> dispatch -> tracking -> POD
    -> accessorial -> payable -> invoice -> settlement -> margin

WHY THIS IS A SEPARATE JOURNEY
`demo_trucking_journey.py` moves freight on OWN_FLEET equipment: the driver is
an employee, the pay is a payroll input, and there is no counterparty to agree
a rate with. Brokerage is a different business with a different failure mode --
the money leaves the building to a company you do not employ, on terms someone
agreed to over the phone.

WHAT IT DEMONSTRATES, IN ORDER
  1. A carrier whose authority check is 90 days old is REFUSED, and a carrier
     with UNKNOWN authority is refused the same way a REVOKED one is.
  2. The load will not DISPATCH until a rate confirmation is ACCEPTED.
  3. Detention is measured as an EVENT and is not yet a CHARGE.
  4. Delivery is not proof of delivery; the invoice waits for a signed POD.
  5. The carrier payable is derived FROM the confirmation and reconciled
     against it -- an accessorial over its agreed cap is refused by name.
  6. Margin is MODELED until the costs are FINANCIAL_ACTUAL, and the realised
     figure says which part of it is missing.

DEMO / SYNTHETIC. Every event is DEMO_SIMULATED in the database, not just in
this narration. Nothing here is corroborated by a bank, a GL, an ELD or a
telematics feed, and no line claims otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from sqlalchemy import text                                      # noqa: E402
from sqlalchemy.ext.asyncio import (async_sessionmaker,          # noqa: E402
                                    create_async_engine)

from app.trucking import billing as B                            # noqa: E402
from app.trucking import eligibility as EL                       # noqa: E402
from app.trucking import rate_confirmation as RC                 # noqa: E402

ORG_NAME = "DEMO — Cardinal Freight (brokerage desk)"
TODAY = date.today()
NOW = datetime.now(timezone.utc)

LANE = ("Pharr", "TX", "Detroit", "MI")
CUSTOMER_RATE = 512_500          # what the shipper pays us
AGREED_LINEHAUL = 385_000        # what we agreed with the carrier
AGREED_FSC = 44_000
DETENTION_CAP = 30_000


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def rule(char: str = "─", n: int = 78) -> None:
    print(char * n)


def step(n: int, title: str) -> None:
    print(f"\n STEP {n} — {title}")
    rule()


async def journey(dsn: str, org_id: Optional[str] = None) -> dict:
    engine = create_async_engine(dsn, future=True)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:

        # ---- org -------------------------------------------------------
        if org_id:
            org = uuid.UUID(str(org_id))
            row = (await db.execute(
                text("SELECT name FROM public.orgs WHERE id = :i"),
                {"i": org})).first()
            if row is None:
                raise SystemExit(f"no organisation {org} on this database")
            print(f"\n  seeding into existing org {row[0]!r} ({org})")
            # RE-RUNNABLE.
            # `demo_trucking_journey.py` may already have put some of these
            # carriers in this org, and a demo that only works on a virgin
            # database is a demo that fails in front of someone. Clear only
            # THIS journey's freight and let the carrier insert be an upsert.
            await db.execute(text("""
                DELETE FROM public.trucking_loads
                WHERE org_id = :o AND load_number = 'L-31108'"""), {"o": org})
            await db.commit()
        else:
            existing = (await db.execute(
                text("SELECT id FROM public.orgs WHERE name = :n"),
                {"n": ORG_NAME})).first()
            if existing:
                await db.execute(
                    text("DELETE FROM public.orgs WHERE id = :i"),
                    {"i": existing[0]})
                await db.commit()
            org = uuid.uuid4()
            await db.execute(
                text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                {"i": org, "n": ORG_NAME})
            await db.commit()

        cust = uuid.uuid4()
        cust_row = (await db.execute(text("""
            INSERT INTO public.trucking_customers
            (id,org_id,name,payment_terms_days,is_demo)
            VALUES (:i,:o,'Valley Fresh Distributors',30,true)
            ON CONFLICT (org_id, name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id"""), {"i": cust, "o": org})).first()
        cust = cust_row[0]

        # ===============================================================
        step(1, "CARRIER SOURCING.  Three carriers want the load.")

        async def carrier(name, dot, status, source, checked_days_ago,
                          ins_days):
            cid = uuid.uuid4()
            row = (await db.execute(text("""INSERT INTO public.trucking_carriers
                (id,org_id,name,dot_number,mc_number,authority_status,
                 authority_source,authority_checked_at,insurance_expires_on,
                 insurance_source,is_approved,payment_terms_days,is_demo)
                VALUES (:i,:o,:n,:d,:m,:st,:src,:ck,:ins,'BROKER_ENTRY',
                        true,30,true)
                ON CONFLICT (org_id, name) DO UPDATE SET
                    authority_status = EXCLUDED.authority_status,
                    authority_source = EXCLUDED.authority_source,
                    authority_checked_at = EXCLUDED.authority_checked_at,
                    insurance_expires_on = EXCLUDED.insurance_expires_on
                RETURNING id"""),
                {"i": cid, "o": org, "n": name, "d": dot,
                 "m": f"MC-{dot[-6:]}", "st": status, "src": source,
                 "ck": NOW - timedelta(days=checked_days_ago),
                 "ins": TODAY + timedelta(days=ins_days)})).first()
            cid = row[0]
            return cid, type("C", (), {
                "is_approved": True, "authority_status": status,
                "authority_source": source,
                "authority_checked_at": NOW - timedelta(days=checked_days_ago),
                "insurance_expires_on": TODAY + timedelta(days=ins_days)})()

        # AUTHORITY SOURCE: MANUAL_ENTRY, NOT FMCSA_LIVE.
        #
        # These carriers were seeded. No FMCSA lookup has ever run against
        # them — the board's own disclosure lists "FMCSA live lookup" under
        # what is not connected — and the load page renders this field
        # verbatim, so FMCSA_LIVE put the words "fmcsa live" next to a
        # carrier's ACTIVE authority on a screen a broker uses to decide
        # whether to tender freight. Seeded data must never present itself as
        # a government lookup.
        #
        # MANUAL_ENTRY is the truth: a human put this status in the row.
        # check_carrier treats every source except NOT_CONNECTED the same and
        # judges FRESHNESS, so all three demo cases still behave identically —
        # stale at 90 days, unverified, and eligible at 2 days.
        stale_id, stale = await carrier(
            "Sunbelt Haulers", "3011991", "ACTIVE", "MANUAL_ENTRY", 90, 200)
        unknown_id, unknown = await carrier(
            "Rapid Route LLC", "3822114", "UNKNOWN", "NOT_CONNECTED", 0, 200)
        good_id, good = await carrier(
            "Delta Line Transport", "2194844", "ACTIVE", "MANUAL_ENTRY", 2, 180)
        await db.commit()

        for label, c in (("Sunbelt Haulers", stale),
                         ("Rapid Route LLC", unknown),
                         ("Delta Line Transport", good)):
            d = EL.check_carrier(carrier=c, as_of=TODAY)
            mark = "  USE " if d.eligible else "REFUSE"
            print(f"  {mark}  {label:26} {', '.join(d.refusal_codes) or 'eligible'}")
        print("\n  A cached ACTIVE from 90 days ago is not current authority,")
        print("  and UNKNOWN is refused exactly as REVOKED is. Neither is a")
        print("  softer state than the other.")

        # ===============================================================
        step(2, "THE LOAD.  Tendered by the shipper, not yet covered.")
        load = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_loads
            (id,org_id,load_number,customer_id,status,fulfilment_mode,
             carrier_id,origin_city,origin_state,destination_city,
             destination_state,pickup_window_start,delivery_window_end,
             equipment_required,commodity,weight_lbs,miles,
             customer_rate_cents,is_demo)
            VALUES (:i,:o,'L-31108',:c,'BOOKED','BROKERED',:car,
                    :oc,:os,:dc,:ds,:pw,:dw,'REEFER','Romaine',42000,1620,
                    :rate,true)"""),
            {"i": load, "o": org, "c": cust, "car": good_id,
             "oc": LANE[0], "os": LANE[1], "dc": LANE[2], "ds": LANE[3],
             "pw": NOW, "dw": NOW + timedelta(days=2),
             "rate": CUSTOMER_RATE})
        await db.commit()
        print(f"  L-31108   {LANE[0]}, {LANE[1]} -> {LANE[2]}, {LANE[3]}")
        print(f"  reefer, 42,000 lb romaine, 1,620 miles")
        print(f"  shipper pays {money(CUSTOMER_RATE)}")

        load_obj = type("L", (), {
            "id": load, "fulfilment_mode": "BROKERED", "carrier_id": good_id,
            "carrier_rate_cents": AGREED_LINEHAUL + AGREED_FSC,
            "customer_rate_cents": CUSTOMER_RATE, "status": "BOOKED",
            "miles": 1620})()

        # ===============================================================
        step(3, "DISPATCH IS REFUSED.  Nobody has agreed a rate.")
        d = RC.check_dispatch(load=load_obj, ratecon=None)
        print(f"  allowed: {d.allowed}   {', '.join(d.refusal_codes)}")
        print(f"  {d.reasons[0]}")

        # ===============================================================
        step(4, "RATE CONFIRMATION.  Issued, then accepted.")
        terms = RC.parse_terms([
            {"kind": "DETENTION", "rate_cents": 5_000, "unit": "HOUR",
             "free_time_minutes": 120, "cap_cents": DETENTION_CAP},
            {"kind": "TARP", "rate_cents": 7_500, "unit": "FLAT"},
        ])
        document = RC.render_document(
            confirmation_number="RC-31108", carrier_name="Delta Line Transport",
            load_number="L-31108", origin=f"{LANE[0]} {LANE[1]}",
            destination=f"{LANE[2]} {LANE[3]}",
            linehaul_cents=AGREED_LINEHAUL, fuel_surcharge_cents=AGREED_FSC,
            terms=terms, equipment="REEFER", commodity="Romaine")
        sha = RC.document_hash(document)

        rc_id = uuid.uuid4()
        RC.validate_transition(RC.DRAFT, RC.ISSUED)
        RC.validate_transition(RC.ISSUED, RC.ACCEPTED)
        accepted_at = NOW - timedelta(hours=6)
        await db.execute(text("""INSERT INTO public.trucking_rate_confirmations
            (id,org_id,load_id,carrier_id,confirmation_number,linehaul_cents,
             fuel_surcharge_cents,agreed_total_cents,approved_accessorials,
             state,issued_at,accepted_at,accepted_by,accepted_channel,
             document_sha256,is_demo)
            VALUES (:i,:o,:l,:c,'RC-31108',:lh,:fsc,:tot,
                    CAST(:terms AS jsonb),'ACCEPTED',:iss,:acc,
                    'Marisol Vega, Delta Line dispatch','EMAIL',:sha,true)"""),
            {"i": rc_id, "o": org, "l": load, "c": good_id,
             "lh": AGREED_LINEHAUL, "fsc": AGREED_FSC,
             "tot": AGREED_LINEHAUL + AGREED_FSC,
             "terms": __import__("json").dumps([t.as_dict() for t in terms]),
             "iss": NOW - timedelta(hours=8), "acc": accepted_at, "sha": sha})
        await db.execute(text("""UPDATE public.trucking_loads
            SET rate_confirmation_id = :rc, carrier_rate_cents = :r
            WHERE id = :l"""),
            {"rc": rc_id, "r": AGREED_LINEHAUL + AGREED_FSC, "l": load})
        await db.commit()

        for line in document.strip().splitlines():
            print(f"  │ {line}")
        print(f"  sha256 {sha[:32]}…  recorded at acceptance")

        ratecon = type("R", (), {
            "id": rc_id, "state": "ACCEPTED", "load_id": load,
            "carrier_id": good_id, "confirmation_number": "RC-31108",
            "linehaul_cents": AGREED_LINEHAUL,
            "fuel_surcharge_cents": AGREED_FSC,
            "agreed_total_cents": AGREED_LINEHAUL + AGREED_FSC,
            "approved_accessorials": [t.as_dict() for t in terms],
            "accepted_by": "Marisol Vega, Delta Line dispatch",
            "accepted_at": accepted_at})()

        # ===============================================================
        step(5, "DISPATCH.  Now it is allowed.")
        d = RC.check_dispatch(load=load_obj, ratecon=ratecon)
        print(f"  allowed: {d.allowed}")

        async def event(kind, when, source="DEMO_SIMULATED", note=""):
            await db.execute(text("""INSERT INTO public.trucking_load_events
                (id,org_id,load_id,event_type,occurred_at,source,note)
                VALUES (:i,:o,:l,:t,:w,:s,:n)"""),
                {"i": uuid.uuid4(), "o": org, "l": load, "t": kind,
                 "w": when, "s": source, "n": note})

        await db.execute(text(
            "UPDATE public.trucking_loads SET status='DISPATCHED' WHERE id=:l"),
            {"l": load})
        await event("DISPATCHED", NOW - timedelta(hours=5))
        await db.commit()

        # ===============================================================
        step(6, "TRACKING.  Carrier-reported, and labelled as such.")
        timeline = [
            ("ARRIVED_PICKUP", NOW - timedelta(hours=4), "CARRIER_REPORTED"),
            ("LOADED", NOW - timedelta(hours=2), "CARRIER_REPORTED"),
            ("DEPARTED_PICKUP", NOW - timedelta(hours=1), "CARRIER_REPORTED"),
            ("ARRIVED_DELIVERY", NOW + timedelta(hours=30), "CARRIER_REPORTED"),
            ("UNLOADED", NOW + timedelta(hours=33, minutes=45),
             "CARRIER_REPORTED"),
            ("DELIVERED", NOW + timedelta(hours=34), "CARRIER_REPORTED"),
        ]
        for kind, when, source in timeline:
            await event(kind, when, source)
            print(f"  {when.strftime('%b %d %H:%M')}  {kind:18} {source}")
        await db.execute(text(
            "UPDATE public.trucking_loads SET status='DELIVERED' WHERE id=:l"),
            {"l": load})
        await db.commit()
        print("\n  Every one of these is CARRIER_REPORTED. No ELD, no")
        print("  telematics, no GPS ping. The authority ladder puts these at")
        print("  PLATFORM_REPORTED and nothing above it.")

        # ===============================================================
        step(7, "DETENTION.  An event, not yet a charge.")
        detained_minutes = 225          # 3h45 at the receiver
        free = 120
        billable_hours = (detained_minutes - free) / 60
        detention_amount = int(round(billable_hours * 5_000))
        acc_id = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_accessorials
            (id,org_id,load_id,accessorial_type,measured_quantity,
             measured_unit,rate_cents,free_allowance,billable_quantity,
             amount_cents,rate_rule_ref,state,direction)
            VALUES (:i,:o,:l,'DETENTION',:q,'MINUTE',5000,:f,:b,:a,
                    'RC-31108','PROPOSED','CARRIER_PAYABLE')"""),
            {"i": acc_id, "o": org, "l": load, "q": detained_minutes,
             "f": free, "b": billable_hours, "a": detention_amount})
        await db.commit()
        print(f"  measured   {detained_minutes} minutes at the receiver")
        print(f"  free time  {free} minutes, per RC-31108")
        print(f"  billable   {billable_hours:.2f} hours -> "
              f"{money(detention_amount)}")
        print(f"  state      PROPOSED")
        print("\n  Detention happening and detention being payable are")
        print("  different facts. This one is still the first.")

        # ===============================================================
        step(8, "INVOICING IS REFUSED.  Delivered is not proof of delivery.")
        try:
            B.build_invoice(load=load_obj,
                            pod=type("P", (), {"evidence_strength": None})(),
                            accessorials=[])
        except B.BillingRefused as exc:
            print(f"  {exc.code}")
            print(f"  {exc.detail}")

        # ===============================================================
        step(9, "POD.  A signed document, bound to this load.")
        pod_id = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.proof_of_delivery
            (id,org_id,load_id,received_at,receiver_name,signature_kind,
             evidence_strength,exceptions_noted,is_demo)
            VALUES (:i,:o,:l,:w,'M. Okafor, Dock 12','WET_SIGNATURE',
                    'SIGNED_DOCUMENT','none noted',true)"""),
            {"i": pod_id, "o": org, "l": load,
             "w": NOW + timedelta(hours=34, minutes=10)})
        await db.execute(text("""UPDATE public.trucking_loads
            SET pod_id = :p, status = 'POD_RECEIVED' WHERE id = :l"""),
            {"p": pod_id, "l": load})
        await db.commit()
        print("  SIGNED_DOCUMENT, receiver named, no exceptions noted.")

        # ===============================================================
        step(10, "ACCESSORIAL APPROVAL.  A person, by name, at a time.")
        await db.execute(text("""UPDATE public.trucking_accessorials
            SET state='APPROVED', approved_by='dispatch@cardinalfreight.test',
                approved_at=now() WHERE id=:i"""), {"i": acc_id})
        await db.commit()
        print(f"  DETENTION {money(detention_amount)} approved by "
              f"dispatch@cardinalfreight.test")

        # ===============================================================
        step(11, "THE PAYABLE, RECONCILED AGAINST THE CONFIRMATION.")
        detention = type("A", (), {
            "accessorial_kind": "DETENTION", "amount_cents": detention_amount,
            "state": "APPROVED", "direction": "CARRIER_PAYABLE"})()

        over_cap = type("A", (), {
            "accessorial_kind": "DETENTION", "amount_cents": 48_000,
            "state": "APPROVED", "direction": "CARRIER_PAYABLE"})()
        try:
            B.build_settlement(load=load_obj, carrier=good, ratecon=ratecon,
                               accessorials=[over_cap])
        except B.BillingRefused as exc:
            print(f"  REFUSED  {exc.code}")
            print(f"           {exc.detail}")

        settlement = B.build_settlement(
            load=load_obj, carrier=good, ratecon=ratecon,
            accessorials=[detention])
        print(f"\n  linehaul + FSC   {money(settlement.linehaul_cents)}")
        print(f"  accessorials     {money(settlement.accessorial_cents)}")
        print(f"  TOTAL PAYABLE    {money(settlement.total_cents)}")
        print(f"\n  {settlement.derivation_note}")

        st_id = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_settlements
            (id,org_id,load_id,payee_kind,carrier_id,linehaul_cents,
             accessorial_cents,deduction_cents,total_cents,derivation_note,
             state,rate_confirmation_id)
            VALUES (:i,:o,:l,'CARRIER',:c,:lh,:acc,0,:tot,:note,'PROPOSED',
                    :rc)"""),
            {"i": st_id, "o": org, "l": load, "c": good_id,
             "lh": settlement.linehaul_cents,
             "acc": settlement.accessorial_cents,
             "tot": settlement.total_cents,
             "note": settlement.derivation_note, "rc": rc_id})
        await db.commit()

        # ===============================================================
        step(12, "THE INVOICE.  Released by the POD.")
        # THE CUSTOMER SIDE IS A ROW, NOT A LOCAL VARIABLE.
        # It was built inline and never stored, so the invoice cited a
        # detention charge that did not appear anywhere in the load's
        # accessorial list. A buyer reading the load page would see an invoice
        # referencing something the page does not show.
        #
        # Detention billed to the customer and detention owed to the carrier
        # are two rows at two rates -- $75/hour out, $50/hour in -- which is
        # the whole reason they are separate.
        cust_acc_id = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_accessorials
            (id,org_id,load_id,accessorial_type,measured_quantity,
             measured_unit,rate_cents,free_allowance,billable_quantity,
             amount_cents,rate_rule_ref,state,direction,approved_by,
             approved_at)
            VALUES (:i,:o,:l,'DETENTION',:q,'MINUTE',7500,:f,:b,:a,
                    'shipper contract 2026','APPROVED','CUSTOMER_BILLABLE',
                    'dispatch@cardinalfreight.test',now())"""),
            {"i": cust_acc_id, "o": org, "l": load, "q": detained_minutes,
             "f": free, "b": billable_hours,
             "a": int(round(billable_hours * 7_500))})
        await db.commit()

        customer_detention = type("A", (), {
            "accessorial_type": "DETENTION",
            "amount_cents": int(round(billable_hours * 7_500)),
            "state": "APPROVED", "direction": "CUSTOMER_BILLABLE",
            "approved_by": "dispatch@cardinalfreight.test"})()
        inv = B.build_invoice(
            load=load_obj,
            pod=type("P", (), {"evidence_strength": "SIGNED_DOCUMENT"})(),
            accessorials=[customer_detention])
        inv_id = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_invoices
            (id,org_id,customer_id,load_id,invoice_number,linehaul_cents,
             accessorial_cents,total_cents,derivation_note,issued_on,due_on,
             state,paid_cents,is_demo)
            VALUES (:i,:o,:c,:l,'INV-31108',:lh,:acc,:tot,:note,:iss,:due,
                    'SENT',0,true)"""),
            {"i": inv_id, "o": org, "c": cust, "l": load,
             "lh": inv.linehaul_cents, "acc": inv.accessorial_cents,
             "tot": inv.total_cents, "note": inv.derivation_note,
             "iss": TODAY, "due": TODAY + timedelta(days=30)})
        await db.execute(text(
            "UPDATE public.trucking_loads SET invoice_id=:i, status='INVOICED' "
            "WHERE id=:l"), {"i": inv_id, "l": load})
        await db.commit()
        print(f"  linehaul     {money(inv.linehaul_cents)}")
        print(f"  accessorial  {money(inv.accessorial_cents)}")
        print(f"  TOTAL        {money(inv.total_cents)}")
        print(f"  {inv.derivation_note}")

        # ===============================================================
        step(13, "MARGIN.  Modelled, and what it would take to realise it.")
        costs = [
            ("CARRIER_PAY", settlement.total_cents, "PLATFORM_REPORTED",
             "the settlement we propose to pay; not yet remitted"),
            ("INSURANCE_ALLOCATION", 4_100, "MODELED",
             "allocated per load from the annual premium"),
        ]
        for kind, amount, authority, note in costs:
            await db.execute(text("""INSERT INTO public.trucking_load_costs
                (id,org_id,load_id,cost_type,amount_cents,authority,note)
                VALUES (:i,:o,:l,:t,:a,:auth,:n)"""),
                {"i": uuid.uuid4(), "o": org, "l": load, "t": kind,
                 "a": amount, "auth": authority, "n": note})
        await db.commit()

        cost_rows = [type("C", (), {"cost_type": k, "amount_cents": a,
                                    "authority": auth})()
                     for k, a, auth, _ in costs]
        m = B.load_margin(invoice=inv, costs=cost_rows)
        pair = B.margin_pair(invoice=inv, costs=cost_rows,
                             cash_collected_cents=0)
        print(f"  revenue             {money(m.revenue_cents)}")
        print(f"  direct cost         {money(m.direct_cost_cents)}")
        print(f"  MODELED margin      {money(m.contribution_margin_cents)} "
              f"({m.margin_pct}%)   graded {m.cost_authority}")
        print(f"  REALISED            {pair.realised_state}")
        print(f"  {pair.note}")

        await engine.dispose()
        return {
            "org_id": str(org), "load_id": str(load),
            "rate_confirmation_id": str(rc_id),
            "settlement_total": settlement.total_cents,
            "invoice_total": inv.total_cents,
            "margin": m,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=(os.environ.get("FINTRA_INTERVIEW_PG_DSN")
                                      or os.environ.get("FINTRA_HR_PG_DSN", "")))
    ap.add_argument("--org", default=os.environ.get("FINTRA_DEMO_ORG_ID"),
                    help="seed into an existing organisation")
    args = ap.parse_args()
    if not args.dsn:
        raise SystemExit("set FINTRA_INTERVIEW_PG_DSN")

    print("\n" + "=" * 78)
    print(" FINTRA BROKERAGE — THE 3PL FLOW        DEMO / SYNTHETIC DATA")
    print(" source the carrier, agree the rate, move the freight, "
          "pay what was agreed")
    print("=" * 78)

    out = asyncio.run(journey(args.dsn, args.org))

    m = out["margin"]
    print("\n" + "=" * 78)
    print(" WHAT THIS SHOWED")
    print("=" * 78)
    print(f"""
  Two of the three carriers were refused before a rate was ever discussed --
  one on a 90-day-old authority check, one on UNKNOWN authority. Neither
  refusal is softer than the other.

  The load would not dispatch until Delta Line ACCEPTED RC-31108. Their pay,
  {money(out['settlement_total'])}, is derived from that document and
  reconciled against it: the detention claim is inside the agreed cap, and a
  {money(48000)} version of the same claim was refused by name.

  The {money(out['invoice_total'])} invoice was released by a signed POD, not
  by the carrier saying "delivered".

  Contribution margin {money(m.contribution_margin_cents)} ({m.margin_pct}%),
  graded {m.cost_authority} -- and the realised figure is not available,
  because no cash has been collected and the carrier has not been paid.

  NOT CONNECTED, and not claimed: ELD/hours of service, bank settlement, GL
  posting, telematics. Tracking above is CARRIER_REPORTED, which is the
  carrier telling us where they are.

  SCOPE: this is transportation and brokerage. Warehousing, fulfilment and
  inventory are not modelled here and are not claimed.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
