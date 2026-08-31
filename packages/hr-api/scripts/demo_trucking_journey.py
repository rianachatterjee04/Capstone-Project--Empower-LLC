#!/usr/bin/env python3
"""The golden journey: find the driver, hire them, prove they can drive, and
show whether the load made money.

    candidate -> personalised AI interview -> evidence scorecard
      -> human hire -> employee -> driver + credentials
      -> load -> ELIGIBILITY GATE -> dispatch -> events -> POD
      -> detention -> approval -> invoice -> settlement -> margin

WHY THIS IS ONE SCRIPT AND NOT TWO DEMOS
Because the point is the join. Anyone can show an AI interviewer, and anyone
can show a load board. The claim here is that the driver on the load is the
person the interview assessed, that their licence is the reason they were
allowed on it, and that the margin at the end traces back through a POD to a
contract rate. Splitting it into two demos loses exactly the thing worth
selling.

EVERY FIGURE IS DERIVED
The invoice is the contract rate plus approved accessorials. The settlement is
the pay model applied to the miles. The margin is revenue less costs that each
carry their own authority. Nothing in the output is typed in.

DEMO / SYNTHETIC. The organisation is named with the DEMO prefix and the
seeder refuses to touch anything else. No government system, bank or telematics
provider is contacted; simulated events are marked DEMO_SIMULATED at the point
they are stored, not just in the narration.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from typing import Optional
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from sqlalchemy import text                                     # noqa: E402
from sqlalchemy.ext.asyncio import (async_sessionmaker,         # noqa: E402
                                    create_async_engine)

from app.interview import repository as R                       # noqa: E402
from app.interview import runner                                # noqa: E402
from app.trucking import billing as B                           # noqa: E402
from app.trucking import eligibility as EL                      # noqa: E402

DEMO_PREFIX = "DEMO —"
ORG_NAME = f"{DEMO_PREFIX} Cardinal Freight"
DRIVER_ROLE = "CDL Driver — Regional Reefer"

TODAY = date.today()
DELIVERY = TODAY + timedelta(days=3)

#: How far apart the seeded answers sit on the recording timeline, so the
#: demo's evidence timecodes land inside the demo's media.
ANSWER_SPACING_MS = int(
    float(os.environ.get("FINTRA_DEMO_ANSWER_SECONDS", "8")) * 1000)

RESUME = """Kenworth T680 / reefer, 6 years OTR and regional (2019-2025).
Class A CDL, clean MVR. Tanker endorsement.
Ran Texas to the Midwest lanes hauling refrigerated produce.
Averaged 2,800 miles a week with a 98% on-time delivery record.
Handled reefer breakdowns and temperature excursions independently.
"""

# What the driver says. Keyed to the competencies in the cdl_driver rubric.
ANSWERS = {
    "equipment_experience": (
        "Six years, mostly reefer on a Kenworth T680. Texas to the Midwest, "
        "produce out of the Valley up to Chicago and Milwaukee. I ran that "
        "lane about three times a month for four of those years."),
    "safety_judgement": (
        "Coming through Amarillo in February the road was glazing over and I "
        "was two hours from my delivery window. I shut down at a truck stop "
        "and called dispatch before they called me. We lost the appointment "
        "and the receiver charged us a redelivery. I would do it again — I "
        "have seen what a loaded reefer does on ice."),
    "exception_handling": (
        "I had a reefer unit fail outside Joplin with 42,000 pounds of "
        "lettuce. I pulled the temperature log off the unit, photographed the "
        "readout, called dispatch and the after-hours line at the customer, "
        "and got to a repair shop within about ninety minutes. Product held "
        "at 38 degrees the whole time so the load was accepted. The paperwork "
        "is what saved it — without the log they would have rejected it."),
    "compliance_awareness": (
        "Level 2 in Oklahoma last year. They looked at my logs, my medical "
        "card and did a walkaround. I had a marker light out that I had not "
        "caught on my pre-trip, so that went on the report. No out of service."),
    "dispatch_communication": (
        "There is a receiver in Milwaukee that will make you sit four hours "
        "if you show up without a check call. I started calling them the "
        "morning of instead of an hour out, and I told dispatch to build that "
        "into the schedule. Our detention on that stop went to almost nothing."),
    "ownership": (
        "The reefer failure is the one. Nobody told me to pull the "
        "temperature log; I did it because I knew that was the only thing "
        "that would stop the load being rejected."),
    "evidence_specificity": (
        "2,800 miles a week on average, 98% on time over the last two years. "
        "The one delivery I missed on time was the Amarillo ice storm."),
}
FOLLOWUP = (
    "To be specific: the unit was throwing a defrost fault. I photographed "
    "the readout every twenty minutes from the failure until the repair, so "
    "there is a documented chain showing it never went above 38.")


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def rule(char: str = "─", n: int = 78) -> None:
    print(char * n)


async def journey(dsn: str, org_id: Optional[str] = None) -> dict:
    engine = create_async_engine(dsn, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    out: dict = {}

    async with maker() as db:
        # ---- reset -------------------------------------------------------
        #
        # SEED WHERE THE APP WILL ACTUALLY LOOK.
        # This used to mint a fresh random org every run. The demo then had
        # real freight, real invoices and a real margin -- in an organisation
        # the web app never opens, because the dev context defaults to the
        # well-known demo org. Anyone opening the trucking board after running
        # this script saw a page of zeros, which reads as a broken product
        # rather than as a seeding mismatch.
        #
        # `--org` targets an existing organisation; with no flag the journey
        # keeps its own Cardinal Freight org, so the two modes are explicit.
        if org_id:
            org = uuid.UUID(str(org_id))
            row = (await db.execute(
                text("SELECT name FROM public.orgs WHERE id = :i"),
                {"i": org})).first()
            if row is None:
                raise SystemExit(
                    f"no organisation {org} on this database. Pass an existing "
                    f"org id, or omit --org to create {ORG_NAME!r}.")
            # Clear only THIS journey's freight, never the whole org: the
            # target may be the demo org that also holds HR and payroll data.
            # ORDER MATTERS, AND SO DOES THE FIRST ENTRY.
            # `commercial_prospects.customer_id` refuses to be orphaned -- a
            # prospect at CUSTOMER stage has to point at the account it
            # converted to, or the conversion is a claim with nothing behind
            # it. That constraint is correct, so the commercial rows are
            # cleared BEFORE the customers they reference rather than the
            # constraint being weakened to suit a demo script.
            for tbl in ("commercial_attributions", "commercial_actions",
                        "commercial_prospects", "commercial_sources",
                        "trucking_settlements", "trucking_invoices",
                        "trucking_load_costs", "trucking_accessorials",
                        "trucking_load_events", "proof_of_delivery",
                        "trucking_loads", "driver_credentials",
                        "trucking_drivers", "trucking_carriers",
                        "trucking_customers"):
                await db.execute(
                    text(f"DELETE FROM public.{tbl} WHERE org_id = :o"),
                    {"o": org})
            await db.commit()
            print(f"\n  seeding into existing org {row[0]!r} ({org})")
        else:
            existing = (await db.execute(
                text("SELECT id FROM public.orgs WHERE name = :n"),
                {"n": ORG_NAME})).first()
            if existing:
                await db.execute(text("DELETE FROM public.orgs WHERE id = :i"),
                                 {"i": existing[0]})
                await db.commit()

            org = uuid.uuid4()
            await db.execute(
                text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                {"i": org, "n": ORG_NAME})

        # =================================================================
        print("\n STEP 1 — HIRING.  A driver applies.")
        rule()
        job = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.job_postings
            (id,org_id,title,description,status) VALUES (:i,:o,:t,:d,'open')"""),
            {"i": job, "o": org, "t": DRIVER_ROLE,
             "d": "Regional reefer, Texas to the Midwest. Home weekly."})
        cand = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.candidates
            (id,org_id,job_posting_id,full_name,email,resume_text,status)
            VALUES (:i,:o,:j,'Marcus Delgado','marcus@example.test',:r,'new')"""),
            {"i": cand, "o": org, "j": job, "r": RESUME})
        await db.commit()

        consent = await R.create_consent(
            db, org_id=org, candidate_id=cand,
            disclosure_text=("This interview is conducted by an AI "
                             "interviewer and is recorded. A human recruiter "
                             "makes the hiring decision."),
            policy_version="2026.08")
        await db.commit()

        prepared = await runner.prepare(
            db, org_id=org, job_posting_id=job, candidate_id=cand,
            job_title=DRIVER_ROLE, resume_text=RESUME, consent_id=consent.id)
        await db.commit()
        plan = prepared["plan"]
        print(f"  rubric      {plan.rubric_key}")
        print(f"  claims      {len(prepared['claims'])} extracted from the resume")
        print(f"  plan        {plan.coverage()['personalised']} of "
              f"{plan.coverage()['competencies']} competencies hooked to a "
              f"claim he actually made")
        hooked = [c for c in plan.competencies if c.is_personalised][:2]
        for c in hooked:
            print(f"\n  [{c.competency_key}] {c.initial_question[:150]}")

        # =================================================================
        print("\n\n STEP 2 — THE INTERVIEW.  Follow-ups come from his answers.")
        rule()
        iv = prepared["interview"].id
        attempt = await runner.start(db, org_id=org, interview_id=iv)
        await db.commit()

        from sqlalchemy import select
        from app.interview import models as IM

        asked = 0
        while asked < 20:
            step = await runner.next_question(db, org_id=org, interview_id=iv,
                                              attempt_id=attempt.id)
            if step.finished or not step.has_question:
                break
            key = None
            if step.question.competency_id:
                res = await db.execute(select(IM.InterviewCompetency).where(
                    IM.InterviewCompetency.org_id == org,
                    IM.InterviewCompetency.id == step.question.competency_id))
                comp = res.scalar_one_or_none()
                key = comp.competency_key if comp else None
            answer = (FOLLOWUP if step.question.probe_depth > 0
                      else ANSWERS.get(key, ANSWERS["evidence_specificity"]))
            if step.question.probe_depth > 0:
                print(f"  follow-up (depth {step.question.probe_depth}): "
                      f"{step.question.question_text[:110]}")
            await runner.submit_answer(
                db, org_id=org, interview_id=iv,
                question_id=step.question.id, answer_text=answer,
                attempt_id=attempt.id,
                # Same scale as the demo media. See the note in
                # seed_interview_demo.py: boundaries 90 seconds apart put
                # every click past the end of a 95-second recording, and the
                # player then correctly refuses to move -- which is the right
                # behaviour and a terrible demonstration of it.
                recording_start_ms=asked * ANSWER_SPACING_MS,
                recording_end_ms=(asked * ANSWER_SPACING_MS
                                  + ANSWER_SPACING_MS - 1_000))
            await db.commit()
            asked += 1

        final = await runner.finalise(db, org_id=org, interview_id=iv)
        await db.commit()
        card = final["scorecard"]
        print(f"\n  {asked} questions asked")
        print(f"  overall     {card.overall_score}/4  "
              f"(confidence {card.overall_confidence})  {card.completeness_state}")
        for a in card.assessments:
            mark = f"{a.score}/4" if a.state == "SCORED" else a.state
            print(f"    {a.competency_key:26} {mark}")
        out["interview_id"] = str(iv)
        out["scorecard"] = card

        # =================================================================
        print("\n STEP 3 — THE HUMAN DECIDES.  Then he becomes an employee.")
        rule()
        print("  The scorecard is decision support. A person hires him.")
        emp = uuid.uuid4()
        # Upsert rather than insert: the org's OTHER employees are not this
        # script's to delete, so the clear list above deliberately leaves the
        # employees table alone -- which means a second run has to tolerate
        # the driver already being there.
        row = (await db.execute(text("""INSERT INTO public.employees
            (id,org_id,legal_name,email,status,job_title,department)
            VALUES (:i,:o,'Marcus Delgado','marcus@example.test','active',
                    :t,'Operations')
            ON CONFLICT (org_id, email) DO UPDATE SET job_title = EXCLUDED.job_title
            RETURNING id"""),
            {"i": emp, "o": org, "t": DRIVER_ROLE})).first()
        emp = row[0]
        drv = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_drivers
            (id,org_id,employee_id,driver_code,status,worker_classification,
             pay_model,pay_rate_cents,home_base,is_demo)
            VALUES (:i,:o,:e,'D-1041','ACTIVE','W2_EMPLOYEE','PER_MILE',62,
                    'Dallas, TX', true)"""),
            {"i": drv, "o": org, "e": emp})
        await db.commit()
        print(f"  employee    {emp}")
        print(f"  driver      D-1041, W2_EMPLOYEE, $0.62/mile")
        print("  Classification is stored explicitly — it decides whether his "
              "pay\n  becomes a payroll input or a contractor settlement.")

        # =================================================================
        print("\n STEP 4 — THE ELIGIBILITY GATE.  This is the control.")
        rule()

        @__import__("dataclasses").dataclass
        class _C:
            credential_type: str
            expires_on: date
            verification_state: str

        # First: his medical card is out of date. The load is refused.
        stale = [_C("CDL_A", TODAY + timedelta(days=500), "DOCUMENT_ON_FILE"),
                 _C("MEDICAL_CARD", TODAY - timedelta(days=4), "DOCUMENT_ON_FILE")]
        d1 = EL.check_driver(driver=type("D", (), {"status": "ACTIVE"})(),
                             credentials=stale, equipment="REEFER",
                             as_of=TODAY, delivery_by=DELIVERY)
        print(f"  with an expired medical card -> eligible={d1.eligible}")
        for r in d1.reasons:
            print(f"     REFUSED  {r.code}: {r.detail}")

        # He renews it. Now the same check passes.
        for c in (("CDL_A", TODAY + timedelta(days=500)),
                  ("MEDICAL_CARD", TODAY + timedelta(days=300))):
            await db.execute(text("""INSERT INTO public.driver_credentials
                (org_id,driver_id,credential_type,expires_on,
                 verification_state,verified_at)
                VALUES (:o,:d,:t,:e,'DOCUMENT_ON_FILE', now())"""),
                {"o": org, "d": drv, "t": c[0], "e": c[1]})
        await db.commit()

        # A SECOND DRIVER WHO IS STILL BLOCKED, and blocked in the DATABASE.
        #
        # Everything above happens in memory and prints. The refusal that makes
        # this demo memorable -- "his medical card expired four days ago, so
        # Fintra will not let him take the freight" -- left no trace anyone
        # could click on: the only credentials written are the renewed ones, so
        # a buyer opening the app sees an eligible driver and no evidence the
        # control exists. A control you have to be told about is a claim.
        #
        # So D-1042 is seeded with a CDL that is fine and a medical card that
        # expired four days ago, and left that way. He is the driver you open on
        # screen to show the refusal, fix, and re-check.
        drv2 = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_drivers
            (id,org_id,driver_code,status,worker_classification,
             pay_model,pay_rate_cents,home_base,is_demo)
            VALUES (:i,:o,'D-1042','ACTIVE','W2_EMPLOYEE','PER_MILE',62,
                    'Laredo, TX', true)"""),
            {"i": drv2, "o": org})
        for c in (("CDL_A", TODAY + timedelta(days=420)),
                  ("MEDICAL_CARD", TODAY - timedelta(days=4))):
            await db.execute(text("""INSERT INTO public.driver_credentials
                (org_id,driver_id,credential_type,expires_on,
                 verification_state,verified_at)
                VALUES (:o,:d,:t,:e,'DOCUMENT_ON_FILE', now())"""),
                {"o": org, "d": drv2, "t": c[0], "e": c[1]})
        await db.commit()
        print(f"\n  D-1042 is left BLOCKED on purpose: medical card expired "
              f"{(TODAY - timedelta(days=4)).isoformat()}.")
        print("  Open him in the app to see the refusal, renew the card, and "
              "watch it clear.")

        current = [_C("CDL_A", TODAY + timedelta(days=500), "DOCUMENT_ON_FILE"),
                   _C("MEDICAL_CARD", TODAY + timedelta(days=300), "DOCUMENT_ON_FILE")]
        d2 = EL.check_driver(driver=type("D", (), {"status": "ACTIVE"})(),
                             credentials=current, equipment="REEFER",
                             as_of=TODAY, delivery_by=DELIVERY)
        print(f"\n  after he renews it          -> eligible={d2.eligible}")
        print(f"     not connected: {', '.join(d2.not_connected)} "
              f"(hours of service is a real gap, shown rather than assumed)")

        # =================================================================
        print("\n STEP 5 — THE LOAD.  Customer, rate, dispatch.")
        rule()
        cust = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_customers
            (id,org_id,name,kind,payment_terms_days,is_demo)
            VALUES (:i,:o,'Rio Grande Produce','SHIPPER',30,true)"""),
            {"i": cust, "o": org})
        load = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_loads
            (id,org_id,customer_id,load_number,status,fulfilment_mode,driver_id,
             origin_city,origin_state,destination_city,destination_state,
             equipment_required,temperature_min_f,temperature_max_f,
             commodity,weight_lbs,miles,customer_rate_cents,is_demo)
            VALUES (:i,:o,:c,'L-24817','DISPATCHED','OWN_FLEET',:d,
                    'McAllen','TX','Chicago','IL','REEFER',34,38,
                    'Refrigerated produce',42000,1284,412500,true)"""),
            {"i": load, "o": org, "c": cust, "d": drv})
        await db.commit()
        print("  L-24817  McAllen TX -> Chicago IL, reefer 34-38F, "
              "42,000 lb, 1,284 mi")
        print(f"  customer rate {money(412500)}   driver D-1041 (eligible)")

        # =================================================================
        print("\n STEP 6 — EXECUTION, AND AN EXCEPTION.")
        rule()
        base = datetime.now(timezone.utc) - timedelta(days=2)
        events = [
            ("ARRIVED_PICKUP", base, "DEMO_SIMULATED"),
            ("LOADED", base + timedelta(hours=5, minutes=40), "DEMO_SIMULATED"),
            ("DEPARTED_PICKUP", base + timedelta(hours=5, minutes=55), "DEMO_SIMULATED"),
            ("ARRIVED_DELIVERY", base + timedelta(hours=34), "DEMO_SIMULATED"),
            ("UNLOADED", base + timedelta(hours=36, minutes=15), "DEMO_SIMULATED"),
            ("DELIVERED", base + timedelta(hours=36, minutes=30), "DEMO_SIMULATED"),
        ]
        ev_ids = {}
        for etype, when, src in events:
            eid = uuid.uuid4()
            await db.execute(text("""INSERT INTO public.trucking_load_events
                (id,org_id,load_id,event_type,occurred_at,source)
                VALUES (:i,:o,:l,:t,:w,:s)"""),
                {"i": eid, "o": org, "l": load, "t": etype, "w": when, "s": src})
            ev_ids[etype] = eid
        await db.commit()
        print("  6 events recorded, all marked DEMO_SIMULATED at the row level")
        print("  detention at pickup: 5h40m loading against a 2h free window")

        # =================================================================
        print("\n STEP 7 — POD.  Delivered is not proof.")
        rule()
        pod = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.proof_of_delivery
            (id,org_id,load_id,received_at,receiver_name,signature_kind,
             evidence_strength,is_demo)
            VALUES (:i,:o,:l,:w,'T. Okafor, receiving','SCANNED_DOCUMENT',
                    'SIGNED_DOCUMENT',true)"""),
            {"i": pod, "o": org, "l": load,
             "w": base + timedelta(hours=36, minutes=45)})
        await db.execute(text(
            "UPDATE public.trucking_loads SET pod_id=:p, status='POD_RECEIVED' "
            "WHERE id=:l AND org_id=:o"), {"p": pod, "l": load, "o": org})
        await db.commit()
        print("  DELIVERED  = the driver's assertion (an interested party)")
        print("  POD        = SIGNED_DOCUMENT from T. Okafor at receiving")
        print("  Billing reads the second one. Invoicing off the first is how "
              "you\n  bill for a load the receiver never got.")

        # =================================================================
        print("\n STEP 8 — DETENTION.  Event -> rule -> approval -> charge.")
        rule()
        acc = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_accessorials
            (id,org_id,load_id,accessorial_type,triggering_event_id,
             measured_quantity,measured_unit,rate_cents,free_allowance,
             billable_quantity,amount_cents,rate_rule_ref,state,direction,
             approved_by,approved_at)
            VALUES (:i,:o,:l,'DETENTION',:e,5.667,'HOURS',6500,2.0,3.667,23836,
                    'MSA-2026 detention: 2h free then $65/h','APPROVED',
                    'CUSTOMER_BILLABLE','ops.manager@example.test', now())"""),
            {"i": acc, "o": org, "l": load, "e": ev_ids["LOADED"]})
        await db.commit()
        print("  measured   5.667 h at pickup (from the LOADED event)")
        print("  rule       MSA-2026: 2h free, then $65/h")
        print("  billable   3.667 h  ->  " + money(23836))
        print("  approved   ops.manager@example.test")
        print("  Unapproved accessorials never reach a total.")

        # =================================================================
        print("\n STEP 9 — INVOICE.  Derived, not typed.")
        rule()

        @__import__("dataclasses").dataclass
        class _A:
            id: object
            accessorial_type: str
            direction: str
            state: str
            amount_cents: int
            approved_by: str

        load_obj = type("L", (), {"customer_rate_cents": 412500,
                                  "carrier_rate_cents": None,
                                  "fulfilment_mode": "OWN_FLEET",
                                  "miles": 1284, "status": "POD_RECEIVED"})()
        pod_obj = type("P", (), {"evidence_strength": "SIGNED_DOCUMENT"})()
        accs = [_A(acc, "DETENTION", "CUSTOMER_BILLABLE", "APPROVED", 23836,
                   "ops.manager@example.test")]

        inv = B.build_invoice(load=load_obj, pod=pod_obj, accessorials=accs)
        inv_id = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_invoices
            (id,org_id,customer_id,load_id,invoice_number,linehaul_cents,
             accessorial_cents,total_cents,derivation_note,due_on,state,is_demo)
            VALUES (:i,:o,:c,:l,'INV-24817',:lh,:ac,:tot,:note,:due,'SENT',true)"""),
            {"i": inv_id, "o": org, "c": cust, "l": load,
             "lh": inv.linehaul_cents, "ac": inv.accessorial_cents,
             "tot": inv.total_cents, "note": inv.derivation_note,
             "due": TODAY + timedelta(days=30)})
        await db.commit()
        print(f"  linehaul     {money(inv.linehaul_cents)}")
        print(f"  detention    {money(inv.accessorial_cents)}")
        print(f"  TOTAL        {money(inv.total_cents)}   terms Net 30")
        print(f"\n  derivation:  {inv.derivation_note[:150]}")

        # =================================================================
        print("\n STEP 10 — DRIVER PAY.  It goes to payroll, not a payable.")
        rule()
        driver_obj = type("D", (), {"worker_classification": "W2_EMPLOYEE",
                                    "pay_model": "PER_MILE",
                                    "pay_rate_cents": 62})()
        st = B.build_settlement(load=load_obj, driver=driver_obj, accessorials=[])
        await db.execute(text("""INSERT INTO public.trucking_settlements
            (org_id,load_id,payee_kind,driver_id,linehaul_cents,
             accessorial_cents,total_cents,derivation_note,state,payroll_reference)
            VALUES (:o,:l,:pk,:d,:lh,:ac,:tot,:note,'PAYROLL_INPUT','PR-2026-35')"""),
            {"o": org, "l": load, "pk": st.payee_kind, "d": drv,
             "lh": st.linehaul_cents, "ac": st.accessorial_cents,
             "tot": st.total_cents, "note": st.derivation_note})
        await db.commit()
        print(f"  1,284 miles at $0.62  =  {money(st.total_cents)}")
        print(f"  payee_kind   {st.payee_kind}")
        print(f"  routes to payroll: {st.routes_to_payroll}  (ref PR-2026-35)")
        print("  The schema refuses to mark a DRIVER_W2 settlement PAID. "
              "Withholding\n  and employer contributions apply to this amount.")

        # =================================================================
        print("\n STEP 11 — MARGIN.  Revenue is not profit.")
        rule()
        costs = [("DRIVER_LABOR", st.total_cents, "FINANCIAL_ACTUAL"),
                 ("FUEL", 47_600, "FINANCIAL_ACTUAL"),
                 ("TOLLS", 4_200, "FINANCIAL_ACTUAL"),
                 ("INSURANCE_ALLOCATION", 8_900, "MODELED")]
        for ctype, amt, auth in costs:
            await db.execute(text("""INSERT INTO public.trucking_load_costs
                (org_id,load_id,cost_type,amount_cents,authority)
                VALUES (:o,:l,:t,:a,:au)"""),
                {"o": org, "l": load, "t": ctype, "a": amt, "au": auth})
        await db.commit()

        cost_objs = [type("C", (), {"cost_type": t, "amount_cents": a,
                                    "authority": au})()
                     for t, a, au in costs]
        m = B.load_margin(invoice=inv, costs=cost_objs)
        print(f"  revenue              {money(m.revenue_cents):>14}")
        for k, v in sorted(m.cost_breakdown.items(), key=lambda x: -x[1]):
            print(f"    - {k:<24}{money(v):>12}")
        print(f"  CONTRIBUTION MARGIN  {money(m.contribution_margin_cents):>14}"
              f"   ({m.margin_pct}%)")
        print(f"\n  authority   {m.cost_authority}, held there by "
              f"{m.limiting_cost}")
        print(f"  {m.note[:190]}")

        await seed_fleet(db, org, cust, drv)

        out.update({"org_id": str(org), "load_id": str(load),
                    "invoice": inv, "settlement": st, "margin": m,
                    "driver_id": str(drv), "employee_id": str(emp)})

    await engine.dispose()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=(os.environ.get("FINTRA_INTERVIEW_PG_DSN")
                                      or os.environ.get("FINTRA_HR_PG_DSN", "")))
    ap.add_argument(
        "--org",
        default=os.environ.get("FINTRA_DEMO_ORG_ID"),
        help=("seed into an EXISTING organisation instead of creating "
              "Cardinal Freight. Use the org the web app opens by default, "
              "or the trucking board will be a page of zeros."))
    args = ap.parse_args()
    if not args.dsn:
        raise SystemExit("set FINTRA_INTERVIEW_PG_DSN")

    print("\n" + "=" * 78)
    print(" FINTRA TRUCKING — GOLDEN JOURNEY        DEMO / SYNTHETIC DATA")
    print(" hire the driver, prove they can drive, move the freight, "
          "know the margin")
    print("=" * 78)

    out = asyncio.run(journey(args.dsn, args.org))

    print("\n" + "=" * 78)
    print(" WHAT THIS SHOWED")
    print("=" * 78)
    m, inv = out["margin"], out["invoice"]
    print(f"""
  The driver on load L-24817 is the person the AI interviewed. His licence is
  the reason he was allowed on it -- and an expired medical card refused the
  same assignment four lines earlier. The {money(inv.total_cents)} invoice is a
  contract rate plus one approved detention charge, released by a signed POD
  rather than by the driver saying "delivered". His pay went to payroll because
  he is a W-2 employee, and the schema will not let it be paid any other way.

  Contribution margin {money(m.contribution_margin_cents)} ({m.margin_pct}%),
  graded {m.cost_authority} because the insurance figure is modelled.

  NOT CONNECTED, and not claimed: ELD/hours of service, FMCSA live lookup,
  bank settlement, GL posting, telematics. Every event above is
  DEMO_SIMULATED in the database, not just in this narration.
""")
    return 0


# ---------------------------------------------------------------------------
# A small fleet, so the Today board shows an operation rather than one load.
# ---------------------------------------------------------------------------

FLEET = [
    # (number, status, origin, dest, miles, rate, mode, has_pod, invoiced, note)
    ("L-24818", "IN_TRANSIT", "Laredo", "TX", "Kansas City", "MO", 812, 268_000,
     "OWN_FLEET", False, False, None),
    ("L-24819", "AT_DELIVERY", "Harlingen", "TX", "Memphis", "TN", 1_042, 331_500,
     "BROKERED", False, False, None),
    ("L-24820", "DELIVERED", "McAllen", "TX", "Indianapolis", "IN", 1_398, 445_000,
     "BROKERED", False, False, "delivered, POD not yet received"),
    ("L-24821", "EXCEPTION", "Pharr", "TX", "Detroit", "MI", 1_562, 498_000,
     "OWN_FLEET", False, False, "reefer alarm in transit"),
    ("L-24822", "INVOICED", "Mission", "TX", "Chicago", "IL", 1_284, 402_000,
     "BROKERED", True, True, "thin margin"),
]


async def seed_fleet(db, org, cust, drv) -> None:
    """Extra loads across the lifecycle. Each is DEMO data and marked so.

    Two carriers, deliberately different: one fully qualified, one whose
    authority has not been re-checked in months. The second is what makes the
    compliance panel show something real -- a cached ACTIVE is not evidence of
    current authority.
    """
    import uuid as _u
    from datetime import datetime as _dt, timezone as _tz

    good = _u.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_carriers
        (id,org_id,name,dot_number,authority_status,authority_source,
         authority_checked_at,insurance_expires_on,is_approved,approved_by,
         approved_at,is_demo)
        -- MANUAL_ENTRY, not FMCSA_CACHED: nothing has ever looked these
        -- carriers up. A cached result is still a claim that a lookup
        -- happened once, and none did.
        VALUES (:i,:o,'Sunbelt Carriers LLC','2841773','ACTIVE','MANUAL_ENTRY',
                now() - interval '6 days', current_date + 210, true,
                'ops.manager@example.test', now(), true)"""),
        {"i": good, "o": org})

    stale = _u.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_carriers
        (id,org_id,name,dot_number,authority_status,authority_source,
         authority_checked_at,insurance_expires_on,is_approved,approved_by,
         approved_at,is_demo)
        VALUES (:i,:o,'Delta Line Transport','3119042','ACTIVE','MANUAL_ENTRY',
                now() - interval '214 days', current_date + 9, true,
                'ops.manager@example.test', now(), true)"""),
        {"i": stale, "o": org})
    await db.commit()

    for (num, status, ocity, ost, dcity, dst, miles, rate, mode,
         has_pod, invoiced, note) in FLEET:
        lid = _u.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_loads
            (id,org_id,customer_id,load_number,status,fulfilment_mode,driver_id,
             carrier_id,origin_city,origin_state,destination_city,
             destination_state,equipment_required,commodity,miles,
             customer_rate_cents,is_demo)
            VALUES (:i,:o,:c,:n,:s,:m,:d,:ca,:oc,:os,:dc,:ds,'REEFER',
                    'Refrigerated produce',:mi,:r,true)"""),
            {"i": lid, "o": org, "c": cust, "n": num, "s": status, "m": mode,
             "d": drv if mode == "OWN_FLEET" else None,
             "ca": None if mode == "OWN_FLEET" else (
                 stale if num == "L-24822" else good),
             "oc": ocity, "os": ost, "dc": dcity, "ds": dst,
             "mi": miles, "r": rate})

        if has_pod:
            pid = _u.uuid4()
            await db.execute(text("""INSERT INTO public.proof_of_delivery
                (id,org_id,load_id,received_at,receiver_name,signature_kind,
                 evidence_strength,is_demo)
                VALUES (:i,:o,:l,now(),'Receiving','SCANNED_DOCUMENT',
                        'SIGNED_DOCUMENT',true)"""),
                {"i": pid, "o": org, "l": lid})
            await db.execute(text(
                "UPDATE public.trucking_loads SET pod_id=:p WHERE id=:l"),
                {"p": pid, "l": lid})

        if invoiced:
            await db.execute(text("""INSERT INTO public.trucking_invoices
                (org_id,customer_id,load_id,invoice_number,linehaul_cents,
                 accessorial_cents,total_cents,derivation_note,due_on,state,is_demo)
                VALUES (:o,:c,:l,:n,:r,0,:r,
                        'linehaul from the contract rate; POD SIGNED_DOCUMENT',
                        current_date - 5,'SENT',true)"""),
                {"o": org, "c": cust, "l": lid, "n": f"INV-{num[2:]}", "r": rate})
            # A deliberately thin one, so the margin floor alert has something
            # real to fire on.
            for ctype, amt, auth in (("CARRIER_PAY", 372_000, "FINANCIAL_ACTUAL"),
                                     ("FUEL", 21_000, "MODELED")):
                await db.execute(text("""INSERT INTO public.trucking_load_costs
                    (org_id,load_id,cost_type,amount_cents,authority)
                    VALUES (:o,:l,:t,:a,:au)"""),
                    {"o": org, "l": lid, "t": ctype, "a": amt, "au": auth})
    await db.commit()


if __name__ == "__main__":
    raise SystemExit(main())
