#!/usr/bin/env python3
"""Stage 2: turn a real market opportunity into a customer, a load, and cash.

    opportunity artifact (stage 1)
      -> HUMAN saves a prospect        <- the gate. Nothing auto-creates leads.
      -> Growth diagnosis explains the positioning problem
      -> marketing action
      -> opportunity -> customer -> lane and rate
      -> load -> delivery -> POD -> invoice -> cash
      -> direct costs -> contribution margin
      -> attribution back to the original action

WHAT MAKES THIS DIFFERENT FROM A FUNNEL CHART
Every step forward is refused unless the step before it produced evidence. A
prospect cannot become a lead without a human saving it. A lead cannot be
marketed to unless its SOURCE LICENCE permits direct marketing -- FMCSA data
names carriers and does not license outreach, and that refusal is enforced
here rather than described. An invoice needs a POD. Cash needs an invoice.
Attribution needs cash.

The last step is the one most tools skip: at the end it says whether the
original hypothesis actually worked, in dollars, and what grade of evidence
that answer carries.

    python scripts/demo_commercial_loop.py --artifact /tmp/opportunity.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from sqlalchemy import text                                    # noqa: E402
from sqlalchemy.ext.asyncio import (async_sessionmaker,        # noqa: E402
                                    create_async_engine)

from app.commercial import loop as L                           # noqa: E402
from app.trucking import billing as B                          # noqa: E402

DEMO_PREFIX = "DEMO —"
ORG_NAME = os.environ.get("FINTRA_DEMO_ORG_NAME",
                          f"{DEMO_PREFIX} Cardinal Freight")
TODAY = date.today()


def money(c: int) -> str:
    return f"${c / 100:,.2f}"


def rule(n: int = 74) -> None:
    print("─" * n)


class LoopRefused(RuntimeError):
    pass


def choose_prospect(artifact: dict) -> dict:
    """Pick a candidate and check we are ALLOWED to market to it.

    This is the rights gate, and it is the reason the loop cannot simply be
    wired end to end. FMCSA is a public register of carriers; being able to
    read it is not permission to run an outreach campaign against it.
    """
    candidates = artifact.get("market", {}).get("candidates") or []
    if not candidates:
        raise LoopRefused("the market scan named no businesses")

    sources = {s.get("name"): s for s in artifact["market"].get("sources") or []}
    permitted = [
        c for c in candidates
        if sources.get(c.get("source"), {}).get("permits_direct_marketing")
    ]

    chosen = candidates[0]
    src = chosen.get("source")
    may_market = bool(sources.get(src, {}).get("permits_direct_marketing"))

    return {
        "name": chosen.get("name"),
        "source": src,
        "identity_strength": chosen.get("identity_strength"),
        "may_direct_market": may_market,
        "permitted_pool": len(permitted),
        "total_pool": len(candidates),
    }


async def run(dsn: str, artifact: dict) -> dict:
    engine = create_async_engine(dsn, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    out: dict = {}

    async with maker() as db:
        row = (await db.execute(text("SELECT id FROM public.orgs WHERE name=:n"),
                                {"n": ORG_NAME})).first()
        if row is None:
            raise LoopRefused(
                f"{ORG_NAME!r} does not exist. Run "
                f"scripts/demo_trucking_journey.py first — this loop attaches "
                f"to the same demo company.")
        org = row[0]

        # =================================================================
        print("\n STEP 1 — MARKET.  A real scan, and what it does not prove.")
        rule()
        m = artifact["market"]
        print(f"  query        {m['query']['industry']} within "
              f"{m['query']['radius_miles']}mi of {m['query']['zip_code']}")
        print(f"  named        {m['named_businesses']} businesses")
        print(f"  coverage     {m['coverage']['grade']} "
              f"(limited by {m['coverage']['limiting_factor']})")
        print(f"\n  {m['population_note']}")

        prospect = choose_prospect(artifact)
        out["prospect"] = prospect

        # =================================================================
        print("\n STEP 2 — RIGHTS.  May we market to this one?")
        rule()
        print(f"  candidate    {prospect['name']}")
        print(f"  source       {prospect['source'] or 'unattributed'}")
        print(f"  direct marketing permitted: {prospect['may_direct_market']}")
        if not prospect["may_direct_market"]:
            print(
                "\n  REFUSED for outreach. The scan is useful for building a "
                "\n  CARRIER NETWORK, which is what a public carrier register "
                "\n  legitimately supports. It is not a licence to run a "
                "\n  campaign, and the loop will not launder it into one.")
            print("\n  The demo continues from a prospect the sales team "
                  "\n  sourced themselves, which is the honest path.")

        # =================================================================
        print("\n STEP 3 — HUMAN SAVES A LEAD.  Nothing auto-creates one.")
        rule()
        shipper = "Rio Grande Produce"

        # RE-RUNNABLE. Each run used to add another prospect, another action
        # and another attribution row, so the loop's own numbers drifted every
        # time it was shown. Clear what this script owns, then rebuild it.
        await db.execute(text("""
            DELETE FROM public.commercial_sources WHERE org_id = :o"""),
            {"o": org})
        await db.commit()

        # THESE ARE ROWS NOW, NOT PRINTED SENTENCES.
        # The loop used to persist nothing but a customer and an invoice, so
        # the story was true only while this script was running. Every gate
        # below is the real one from `app.commercial.loop`, and the schema
        # refuses the same things it does.
        async def source(name, kind, permits, note):
            row = (await db.execute(text("""
                INSERT INTO public.commercial_sources
                (id,org_id,name,kind,permits_direct_marketing,licence_note,
                 retrieved_at,is_demo)
                VALUES (:i,:o,:n,:k,:p,:l,now(),true)
                ON CONFLICT (org_id, name) DO UPDATE SET
                    permits_direct_marketing = EXCLUDED.permits_direct_marketing,
                    licence_note = EXCLUDED.licence_note
                RETURNING id"""),
                {"i": uuid.uuid4(), "o": org, "n": name, "k": kind,
                 "p": permits, "l": note})).first()
            await db.commit()
            return row[0]

        register_src = await source(
            prospect["source"] or "FMCSA carrier register", "PUBLIC_REGISTER",
            False,
            "read-only public register; carries no outreach licence")
        sales_src = await source(
            "Sales-sourced (inbound enquiry)", "SELF_SOURCED", True,
            "the shipper contacted us; we hold their enquiry")

        # The observed candidate from the scan. It stays OBSERVED, because no
        # human saved it and the schema will not let it move without one.
        observed_id = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.commercial_prospects
            (id,org_id,source_id,name,identity_strength,stage,is_demo)
            VALUES (:i,:o,:s,:n,:idn,'OBSERVED',true)"""),
            {"i": observed_id, "o": org, "s": register_src,
             "n": prospect["name"] or "unnamed candidate",
             "idn": (prospect.get("identity_strength") or "NAMED_ONLY").upper()})

        # And the one a person actually saved.
        prospect_id = uuid.uuid4()
        _ = shipper
        await db.execute(text("""INSERT INTO public.commercial_prospects
            (id,org_id,source_id,name,city,state,identity_strength,stage,
             saved_by,saved_at,is_demo)
            VALUES (:i,:o,:s,:n,'McAllen','TX','SELF_IDENTIFIED','SAVED',
                    'dana.ruiz@cardinalfreight.test',now(),true)"""),
            {"i": prospect_id, "o": org, "s": sales_src, "n": shipper})
        await db.commit()

        print(f"  a person saved:  {shipper}")
        print(f"  saved by         dana.ruiz@cardinalfreight.test")
        print(f"  origin           inbound enquiry, sales-sourced")
        print()
        print(f"  The scan's own candidate, {prospect['name']}, stays OBSERVED.")
        try:
            L.check_stage_change(current="OBSERVED", target="CONTACTED",
                                 saved_by=None)
        except L.LoopRefused as exc:
            print(f"  REFUSED to advance it: {exc.code}")
            print(f"  {exc.detail}")

        print()
        print("  And spending against it is refused before the spend is "
              "recorded:")
        try:
            L.check_action(
                source=type("S", (), {
                    "name": prospect["source"], "kind": "PUBLIC_REGISTER",
                    "permits_direct_marketing": False, "licence_note": ""})(),
                prospect_stage="OBSERVED")
        except L.LoopRefused as exc:
            print(f"  REFUSED: {exc.code}")
            print(f"  {exc.detail}")

        # =================================================================
        print("\n STEP 4 — GROWTH.  Why they were not being found.")
        rule()
        diag = artifact.get("diagnosis") or {}
        site = artifact.get("website") or {}
        if diag.get("findings"):
            print(f"  read         {site.get('url')} "
                  f"(http {site.get('http_status')}, "
                  f"{site.get('duration_ms')}ms, robots honoured)")
            for f in diag["findings"]:
                print(f"    [{f['severity']:6}] {f['issue']} — {f['why'][:76]}")
            print(f"\n  authority    {diag.get('authority')}")
            print(f"  {diag.get('note')}")
        else:
            print("  no website was read in stage 1")

        # =================================================================
        print("\n STEP 5 — MARKETING ACTION.  One, recorded.")
        rule()
        action_id = uuid.uuid4()
        action_cost = 180_000       # $1,800
        await db.execute(text("""INSERT INTO public.commercial_actions
            (id,org_id,prospect_id,action_kind,description,occurred_on,
             spend_cents,spend_authority,spend_source_ref,hypothesis,is_demo)
            VALUES (:i,:o,:p,'CONTENT',:d,:on,:s,'FINANCIAL_ACTUAL',
                    'AP invoice 2026-0431',:h,true)"""),
            {"i": action_id, "o": org, "p": prospect_id,
             "d": ("lane-specific outbound and a landing page for "
                   "McAllen to Chicago reefer"),
             "on": TODAY - timedelta(days=45), "s": action_cost,
             "h": ("the lane page is what the shipper searched for; the "
                   "homepage never named a lane")})
        await db.commit()
        print(f"  action       lane-specific outbound + landing page for "
              f"McAllen→Chicago reefer")
        print(f"  cost         {money(action_cost)}  (FINANCIAL_ACTUAL — an "
              f"invoice we paid, AP 2026-0431)")
        print(f"  id           {action_id}")

        # =================================================================
        print("\n STEP 6 — CUSTOMER.  The lead converts.")
        rule()
        # ATTACH TO THE ACCOUNT THAT ACTUALLY SHIPPED.
        # This used to create its own customer by name, so in an org where the
        # freight demo had seeded a differently-named shipper the loop
        # attributed against an account with no loads and reported TOO_EARLY --
        # a true statement about the wrong customer.
        cust = (await db.execute(text("""
            SELECT c.id, c.name, count(l.id) AS loads
            FROM public.trucking_customers c
            LEFT JOIN public.trucking_loads l
              ON l.customer_id = c.id AND l.org_id = c.org_id
            WHERE c.org_id = :o
            GROUP BY c.id, c.name
            ORDER BY loads DESC, c.created_at
            LIMIT 1"""), {"o": org})).first()
        if cust is not None and int(cust[2] or 0) > 0:
            shipper = cust[1]
            print(f"  attaching to the account that already has freight: "
                  f"{shipper}")
        else:
            cust = (await db.execute(text(
                "SELECT id FROM public.trucking_customers "
                "WHERE org_id=:o AND name=:n"),
                {"o": org, "n": shipper})).first()
        if cust is None:
            cid = uuid.uuid4()
            await db.execute(text("""INSERT INTO public.trucking_customers
                (id,org_id,name,kind,payment_terms_days,is_demo)
                VALUES (:i,:o,:n,'SHIPPER',30,true)"""),
                {"i": cid, "o": org, "n": shipper})
            await db.commit()
        else:
            cid = cust[0]

        await db.execute(text("""UPDATE public.trucking_customers
            SET prospect_id = :p WHERE id = :c AND org_id = :o"""),
            {"p": prospect_id, "c": cid, "o": org})
        await db.execute(text("""UPDATE public.commercial_prospects
            SET stage='CUSTOMER', customer_id=:c, converted_at=now()
            WHERE id=:p AND org_id=:o"""),
            {"c": cid, "p": prospect_id, "o": org})
        await db.commit()
        print(f"  customer     {shipper}  (Net 30)")
        print(f"  traced to    the prospect dana.ruiz saved, and to the "
              f"action above")

        # =================================================================
        print("\n STEP 7 — LOADS.  What they actually shipped.")
        rule()
        loads = (await db.execute(text("""
            SELECT l.load_number, l.status, i.total_cents, i.paid_cents, i.state
            FROM public.trucking_loads l
            LEFT JOIN public.trucking_invoices i
              ON i.load_id = l.id AND i.org_id = l.org_id
            WHERE l.org_id=:o AND l.customer_id=:c
            ORDER BY l.load_number"""), {"o": org, "c": cid})).all()

        invoiced = sum(int(r[2] or 0) for r in loads)
        collected = sum(int(r[3] or 0) for r in loads)
        for ln, st, tot, paid, istate in loads:
            print(f"    {ln:10} {st:14} "
                  f"{money(int(tot or 0)):>12} invoiced  "
                  f"{money(int(paid or 0)):>12} collected  {istate or '—'}")
        print(f"\n  loads        {len(loads)}")
        print(f"  invoiced     {money(invoiced)}")
        print(f"  collected    {money(collected)}")

        # =================================================================
        print("\n STEP 8 — CASH.  Collect one invoice, for real.")
        rule()
        target = (await db.execute(text("""
            SELECT id, invoice_number, total_cents FROM public.trucking_invoices
            WHERE org_id=:o AND customer_id=:c AND state IN ('SENT','ISSUED')
            ORDER BY issued_on LIMIT 1"""), {"o": org, "c": cid})).first()
        if target:
            await db.execute(text("""
                UPDATE public.trucking_invoices
                SET paid_cents=total_cents, paid_at=now(), state='PAID'
                WHERE id=:i AND org_id=:o"""), {"i": target[0], "o": org})
            await db.commit()
            collected += int(target[2])
            print(f"  {target[1]} paid in full: {money(int(target[2]))}")
            print("  CASH is not revenue and not margin. This is the third of "
                  "the\n  three truths, and it is the only one a bank could "
                  "corroborate —\n  which is NOT_CONNECTED here.")
        else:
            print("  no open invoice to collect")

        # =================================================================
        print("\n STEP 9 — MARGIN.  On everything this customer shipped.")
        rule()
        costs = (await db.execute(text("""
            SELECT c.cost_type, SUM(c.amount_cents),
                   MIN(CASE c.authority WHEN 'MODELED' THEN 0
                        WHEN 'PLATFORM_REPORTED' THEN 1
                        WHEN 'CORROBORATED' THEN 2 ELSE 3 END)
            FROM public.trucking_load_costs c
            JOIN public.trucking_loads l
              ON l.id = c.load_id AND l.org_id = c.org_id
            WHERE c.org_id=:o AND l.customer_id=:c
            GROUP BY c.cost_type"""), {"o": org, "c": cid})).all()

        AUTH = ["MODELED", "PLATFORM_REPORTED", "CORROBORATED", "FINANCIAL_ACTUAL"]
        total_cost = sum(int(r[1] or 0) for r in costs)
        weakest = min([int(r[2]) for r in costs], default=3)

        print(f"  revenue                {money(invoiced):>14}")
        for ctype, amt, _ in sorted(costs, key=lambda r: -int(r[1] or 0)):
            print(f"    - {ctype:<22}{money(int(amt or 0)):>12}")
        margin = invoiced - total_cost
        print(f"  CONTRIBUTION MARGIN    {money(margin):>14}"
              f"   ({round(100.0*margin/invoiced,2) if invoiced else 0}%)")
        print(f"  authority              {AUTH[weakest]}")

        # =================================================================
        print("\n STEP 10 — DID IT WORK?  The question most tools skip.")
        rule()
        actions = (await db.execute(text("""
            SELECT action_kind, spend_cents, spend_authority
            FROM public.commercial_actions
            WHERE org_id=:o AND prospect_id=:p"""),
            {"o": org, "p": prospect_id})).mappings().all()
        inv_rows = (await db.execute(text("""
            SELECT total_cents, paid_cents FROM public.trucking_invoices
            WHERE org_id=:o AND customer_id=:c"""),
            {"o": org, "c": cid})).mappings().all()
        cost_rows = (await db.execute(text("""
            SELECT k.cost_type, k.amount_cents, k.authority
            FROM public.trucking_load_costs k
            JOIN public.trucking_loads l
              ON l.id=k.load_id AND l.org_id=k.org_id
            WHERE k.org_id=:o AND l.customer_id=:c"""),
            {"o": org, "c": cid})).mappings().all()

        attr = L.attribute(
            actions=[type("A", (), dict(a))() for a in actions],
            invoices=[type("I", (), dict(i))() for i in inv_rows],
            costs=[type("C", (), dict(c))() for c in cost_rows],
            loads_count=len(loads))

        await db.execute(text("""INSERT INTO public.commercial_attributions
            (id,org_id,prospect_id,customer_id,spend_cents,revenue_cents,
             direct_cost_cents,contribution_margin_cents,cash_collected_cents,
             loads_count,verdict,grade,basis,note,is_demo)
            VALUES (:i,:o,:p,:c,:s,:r,:dc,:cm,:cash,:n,:v,:g,:b,:note,true)"""),
            {"i": uuid.uuid4(), "o": org, "p": prospect_id, "c": cid,
             "s": attr.spend_cents, "r": attr.revenue_cents,
             "dc": attr.direct_cost_cents,
             "cm": attr.contribution_margin_cents,
             "cash": attr.cash_collected_cents, "n": attr.loads_count,
             "v": attr.verdict, "g": attr.grade, "b": attr.basis,
             "note": attr.note})
        await db.commit()

        net, roas, verdict = (attr.net_cents, attr.margin_per_dollar,
                              attr.verdict)
        print(f"  marketing spend        {money(attr.spend_cents):>14}  "
              f"FINANCIAL_ACTUAL")
        print(f"  contribution margin    "
              f"{money(attr.contribution_margin_cents):>14}  {attr.grade}")
        print(f"  net of the action      {money(attr.net_cents):>14}")
        print(f"  margin per $ spent     {str(attr.margin_per_dollar):>14}")
        print()
        print(f"  VERDICT   {attr.verdict}")
        print(f"  GRADE     {attr.grade}"
              + (f" — held there by the {attr.limiting_input}."
                 if attr.limiting_input else "."))
        print(f"  BASIS     {attr.basis}")
        print(f"  {attr.note}")
        print()
        for c in attr.caveats:
            print(f"  · {c}")
        print()
        print(f"  Stored as a row. Open it at /api/commercial/loop/"
              f"{prospect_id}")

        out.update({"org": str(org), "customer": shipper, "loads": len(loads),
                    "invoiced": invoiced, "collected": collected,
                    "margin": margin, "action_cost": action_cost,
                    "net": net, "roas": roas, "authority": attr.grade,
                    "verdict": verdict, "prospect_id": str(prospect_id),
                    "attribution": attr.as_dict()})

    await engine.dispose()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--dsn", default=(os.environ.get("FINTRA_INTERVIEW_PG_DSN")
                                      or os.environ.get("FINTRA_HR_PG_DSN", "")))
    args = ap.parse_args()
    if not args.dsn:
        raise SystemExit("set FINTRA_INTERVIEW_PG_DSN")

    with open(args.artifact, encoding="utf-8") as fh:
        artifact = json.load(fh)

    print("\n" + "=" * 74)
    print(" FINTRA TRUCKING — THE COMMERCIAL LOOP      DEMO / SYNTHETIC")
    print(" find the opportunity, win the customer, move the freight,")
    print(" and say whether it made money")
    print("=" * 74)

    try:
        asyncio.run(run(args.dsn, artifact))
    except LoopRefused as exc:
        print(f"\n  REFUSED: {exc}\n")
        return 1
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
