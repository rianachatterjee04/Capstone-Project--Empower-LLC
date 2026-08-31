"""Every number on the Today board, and the rows behind it.

THE PROBLEM THIS SOLVES
The board's tiles carried a `drill` field that read

    "trucking_loads where status is not terminal"

-- a prose description of a SQL predicate, rendered on a screen shown to a
buyer. It was not a link, nothing consumed it, and it told an operator nothing
they could act on. A number with no way through to the rows is a number an
operator has to take on faith, which is the opposite of what this product
claims to be for.

THE PROPERTY THAT MATTERS
A drill-through that disagrees with its tile is worse than no drill-through:
the operator now has two numbers and no way to tell which is wrong. The
temptation is to write the count query and the list query separately, and they
drift the first time someone edits one of them.

So a Drill owns ONE `source` and ONE `where`. The tile runs
`SELECT <aggregate> FROM <source> WHERE <where>`; the drill runs
`SELECT <columns> FROM <source> WHERE <where>`. They cannot diverge without
someone editing the same string that feeds both, and `test_today_drilldown.py`
reconciles every key against its own tile on real data.

WHAT A DRILL IS NOT
It is not a general query interface. The keys are a closed set, the SQL is
written here rather than assembled from request parameters, and the org filter
is part of every predicate rather than something a caller supplies. A drill
endpoint that took a WHERE clause would be a tenant-isolation hole with a
friendly name.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

DRILLDOWN_VERSION = "drilldown-2026.08.29"

#: How a tile's value is expressed. `count` is a row count; `cents` is a money
#: total the rows must sum to.
COUNT = "count"
CENTS = "cents"


@dataclass(frozen=True)
class Drill:
    key: str
    #: What the operator is looking at, in their words.
    label: str
    #: What clicking it lets them do next. Shown under the list.
    action: str
    source: str
    where: str
    columns: str
    order_by: str
    unit: str = COUNT
    #: The aggregate for the tile. For CENTS drills this must sum the same
    #: expression the row list exposes as `amount_cents`.
    aggregate: str = "count(*)"
    #: Which of `columns` is the row's own id, for linking onward.
    id_column: str = "id"

    def count_sql(self) -> str:
        return f"SELECT {self.aggregate} FROM {self.source} WHERE {self.where}"

    def rows_sql(self, limit: int) -> str:
        return (f"SELECT {self.columns} FROM {self.source} "
                f"WHERE {self.where} ORDER BY {self.order_by} "
                f"LIMIT {int(limit)}")


#: A load whose contribution margin is at or below this is worth a call before
#: it is repeated. Not a hard rule and not a refusal -- a thin load can be the
#: right load -- but a 2% lane that nobody looked at is how a quarter goes.
#:
#: ONE FLOOR. The margin panel on the same board already had a floor of 15%,
#: hard-coded in the router. A first version of the tile below picked its own
#: number, and the screen then said "Loads at or under 8% margin: 1" directly
#: above "1 load below the 15% floor" -- two thresholds, one page, no way for a
#: buyer to know which one the business runs on. Both read from here now.
MARGIN_FLOOR_PCT = 15.0

#: Kept as an alias so the name used at the call sites stays readable.
THIN_MARGIN_PCT = MARGIN_FLOOR_PCT

#: Statuses a load is no longer working through.
_TERMINAL = "('DELIVERED','POD_RECEIVED','INVOICED','SETTLED','CANCELLED')"
_MOVING = ("('DISPATCHED','IN_TRANSIT','AT_PICKUP','PICKED_UP','AT_DELIVERY')")
_OPEN_INVOICE = "('ISSUED','SENT','PARTIALLY_PAID')"

_LOAD_COLUMNS = ("l.id, l.load_number, l.status, l.fulfilment_mode, "
                 "l.origin_city, l.origin_state, "
                 "l.destination_city, l.destination_state, "
                 "l.pickup_window_start, l.delivery_window_end, "
                 "l.equipment_required, l.commodity, l.miles, "
                 "l.customer_rate_cents AS amount_cents")
_INVOICE_COLUMNS = ("i.id, i.invoice_number, i.state, i.issued_on, i.due_on, "
                    "i.total_cents, i.paid_cents, "
                    "(i.total_cents - i.paid_cents) AS amount_cents")
_SETTLEMENT_COLUMNS = ("s.id, s.load_id, s.payee_kind, s.state, "
                       "s.linehaul_cents, s.accessorial_cents, "
                       "s.deduction_cents, s.approved_at, s.derivation_note, "
                       "s.total_cents AS amount_cents")

DRILLS: Dict[str, Drill] = {d.key: d for d in (
    # ---- operations ------------------------------------------------------
    # MARGIN IS THE ONE NUMBER A BROKER RUNS ON, and the board had no tile for
    # it. Every other question -- what is moving, what is stuck, who owes us --
    # was one click away, and "which of these did we barely make anything on"
    # was not on the screen at all. The load page has always shown the margin;
    # you had to already suspect a load to go and look.
    #
    # MODELED, and it says so. This divides revenue by the costs recorded
    # against the load, whose authorities differ per row -- so the percentage
    # is only as good as its weakest cost, exactly as the load page explains.
    # It is a prompt to look, not a measured result.
    # REVENUE HERE MUST MEAN WHAT IT MEANS ON THE MARGIN TABLE.
    #
    # This used `l.customer_rate_cents` — the agreed linehaul rate — while
    # app/trucking/billing.py computes contribution margin from
    # `linehaul + accessorials` off the invoice. So the same page showed a tile
    # reading "Loads at or under 15% margin: 2" above a margin table in which
    # only one row was under 15%: L-31108 is 13.79% on linehaul alone and
    # 15.94% once its accessorial revenue is counted.
    #
    # Understating revenue overstates thinness, which on this screen means
    # sending a broker to renegotiate a load that is not actually thin. Two
    # numbers for one question, disagreeing, on one page.
    #
    # Invoice revenue when the load has been invoiced; the agreed rate when it
    # has not, because an uninvoiced load has no accessorials recorded yet.
    Drill(key="thin_margin",
          label="Loads at or under %g%% margin" % THIN_MARGIN_PCT,
          action=("MODELED margin, graded by the weakest cost on each load. "
                  "Open one to see which cost is holding the grade down and "
                  "whether the rate, the accessorials or the carrier pay is "
                  "the thing to change."),
          source=("public.trucking_loads l "
                  "LEFT JOIN LATERAL (SELECT COALESCE(SUM(c.amount_cents),0) AS cost "
                  "FROM public.trucking_load_costs c "
                  "WHERE c.load_id = l.id AND c.org_id = l.org_id) k ON TRUE "
                  "LEFT JOIN LATERAL (SELECT COALESCE(i.linehaul_cents,0) "
                  "       + COALESCE(i.accessorial_cents,0) AS rev "
                  "FROM public.trucking_invoices i "
                  "WHERE i.load_id = l.id AND i.org_id = l.org_id "
                  "ORDER BY i.created_at DESC LIMIT 1) inv ON TRUE"),
          where=("l.org_id = :o AND k.cost > 0 "
                 "AND COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents) > 0 "
                 "AND (COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents) - k.cost) * 100.0 "
                 f"    <= COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents) * {THIN_MARGIN_PCT}"),
          columns=(_LOAD_COLUMNS + ", k.cost AS direct_cost_cents, "
                   "COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents) AS revenue_cents, "
                   "round((COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents) - k.cost) * 100.0 "
                   "      / NULLIF(COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents),0), 2) AS margin_pct"),
          order_by=("(COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents) - k.cost) * 1.0 "
                    "/ NULLIF(COALESCE(NULLIF(inv.rev,0), l.customer_rate_cents),0), l.load_number")),
    Drill(key="active_loads",
          label="Active loads",
          action="Open a load to see its stops, costs and documents.",
          source="public.trucking_loads l",
          where=f"l.org_id = :o AND l.status NOT IN {_TERMINAL}",
          columns=_LOAD_COLUMNS,
          order_by="l.pickup_window_start NULLS LAST, l.load_number"),
    Drill(key="in_transit",
          label="In transit",
          action="Loads between dispatch and the delivery door.",
          source="public.trucking_loads l",
          where=f"l.org_id = :o AND l.status IN {_MOVING}",
          columns=_LOAD_COLUMNS,
          order_by="l.delivery_window_end NULLS LAST, l.load_number"),
    Drill(key="exceptions",
          label="Exceptions",
          action="Each of these needs a call. Work the oldest first.",
          source="public.trucking_loads l",
          where="l.org_id = :o AND l.status = 'EXCEPTION'",
          columns=_LOAD_COLUMNS,
          order_by="l.pickup_window_start NULLS LAST, l.load_number"),
    Drill(key="delivered_no_pod",
          label="Delivered, no POD",
          action=("None of these can be invoiced. Chase the signed document, "
                  "not the delivery status."),
          source="public.trucking_loads l",
          where="l.org_id = :o AND l.status = 'DELIVERED' AND l.pod_id IS NULL",
          columns=_LOAD_COLUMNS,
          order_by="l.delivery_window_end NULLS LAST, l.load_number"),

    Drill(key="unconfirmed_brokered",
          label="Brokered, no accepted rate",
          action=("These will not dispatch. Issue a rate confirmation and get "
                  "it accepted, or the rate gets discovered at settlement "
                  "time, by the carrier."),
          source=("public.trucking_loads l "
                  "LEFT JOIN public.trucking_rate_confirmations rc "
                  "  ON rc.id = l.rate_confirmation_id "
                  "  AND rc.org_id = l.org_id AND rc.state = 'ACCEPTED'"),
          where=("l.org_id = :o AND l.fulfilment_mode = 'BROKERED' "
                 "AND l.status NOT IN ('CANCELLED','SETTLED') "
                 "AND rc.id IS NULL"),
          columns=_LOAD_COLUMNS,
          order_by="l.pickup_window_start NULLS LAST, l.load_number"),

    # ---- money -----------------------------------------------------------
    Drill(key="open_ar",
          label="Open AR",
          action="Invoiced and unpaid. This is not cash.",
          source="public.trucking_invoices i",
          where=f"i.org_id = :o AND i.state IN {_OPEN_INVOICE}",
          columns=_INVOICE_COLUMNS,
          order_by="i.due_on NULLS LAST, i.invoice_number",
          unit=CENTS,
          aggregate="COALESCE(SUM(i.total_cents - i.paid_cents), 0)"),
    Drill(key="overdue_ar",
          label="Overdue AR",
          action="Past the due date on the invoice. Call these today.",
          source="public.trucking_invoices i",
          where=(f"i.org_id = :o AND i.state IN {_OPEN_INVOICE} "
                 f"AND i.due_on < :d"),
          columns=_INVOICE_COLUMNS,
          order_by="i.due_on, i.invoice_number",
          unit=CENTS,
          aggregate="COALESCE(SUM(i.total_cents - i.paid_cents), 0)"),
    Drill(key="unbilled_delivered",
          label="Unbilled delivered",
          action=("Earned and not yet invoiced. Not revenue and not AR — "
                  "invoice these to turn them into either."),
          source="public.trucking_loads l",
          where=("l.org_id = :o AND l.pod_id IS NOT NULL "
                 "AND l.invoice_id IS NULL"),
          columns=_LOAD_COLUMNS,
          order_by="l.delivery_window_end NULLS LAST, l.load_number",
          unit=CENTS,
          aggregate="COALESCE(SUM(l.customer_rate_cents), 0)"),
    Drill(key="carrier_pay_due",
          label="Carrier pay due",
          action="Approved and proposed carrier settlements.",
          source="public.trucking_settlements s",
          where=("s.org_id = :o AND s.payee_kind = 'CARRIER' "
                 "AND s.state IN ('APPROVED','PROPOSED')"),
          columns=_SETTLEMENT_COLUMNS,
          order_by="s.approved_at NULLS LAST, s.id",
          unit=CENTS,
          aggregate="COALESCE(SUM(s.total_cents), 0)"),
    Drill(key="payroll_obligation",
          label="Payroll obligation",
          action=("W-2 driver earnings routed to payroll. Withholding and "
                  "employer contributions are additional to this figure."),
          source="public.trucking_settlements s",
          where=("s.org_id = :o AND s.payee_kind = 'DRIVER_W2' "
                 "AND s.state = 'PAYROLL_INPUT'"),
          columns=_SETTLEMENT_COLUMNS,
          order_by="s.approved_at NULLS LAST, s.id",
          unit=CENTS,
          aggregate="COALESCE(SUM(s.total_cents), 0)"),

    # ---- compliance ------------------------------------------------------
    # The predicate is `expires_on <= today + 30 days` with NO lower bound, so
    # it has always included credentials that expired WEEKS AGO -- and called
    # them "expiring within 30 days". Those are not the same fact and not the
    # same urgency: one is a driver to schedule an appointment for, the other
    # is a driver who cannot legally take freight this morning. On a compliance
    # tile that distinction is the entire point, so the label states both and
    # the rows sort the expired ones to the top.
    Drill(key="expiring_credentials",
          label="Credentials expired or expiring within 30 days",
          action=("Anything with a date in the past is already refusing "
                  "dispatch. A credential that expires mid-load makes the "
                  "driver ineligible before the freight is delivered."),
          source=("public.driver_credentials c "
                  "JOIN public.trucking_drivers d "
                  "  ON d.id = c.driver_id AND d.org_id = c.org_id"),
          where=("c.org_id = :o AND c.expires_on IS NOT NULL "
                 "AND c.expires_on <= :soon"),
          columns=("c.id, d.driver_code, d.status AS driver_status, "
                   "c.credential_type, c.issuing_authority, "
                   "c.verification_state, c.expires_on, "
                   "(c.expires_on < CURRENT_DATE) AS already_expired"),
          order_by="c.expires_on",
          id_column="id"),
    Drill(key="carrier_issues",
          label="Carriers that cannot be used",
          action=("Refresh authority from FMCSA, or get a current insurance "
                  "certificate, before tendering to these."),
          source="public.trucking_carriers c",
          where=("c.org_id = :o AND ("
                 "c.authority_status <> 'ACTIVE' "
                 "OR c.insurance_expires_on IS NULL "
                 "OR c.insurance_expires_on < :d "
                 "OR c.authority_checked_at IS NULL "
                 "OR c.authority_checked_at < now() - interval '30 days')"),
          columns=("c.id, c.name, c.mc_number, c.dot_number, "
                   "c.authority_status, c.authority_source, "
                   "c.authority_checked_at, c.insurance_expires_on"),
          order_by="c.name"),

    # ---- people ----------------------------------------------------------
    Drill(key="interviews_completed",
          label="Interviews completed",
          action="Open one to hear the recording behind each assessment.",
          source=("public.interviews i "
                  "JOIN public.job_postings j "
                  "  ON j.id = i.job_posting_id AND j.org_id = i.org_id"),
          where="i.org_id = :o AND i.status = 'COMPLETED'",
          columns=("i.id, i.candidate_id, j.title AS job_title, i.status, "
                   "i.started_at, i.ended_at"),
          order_by="i.ended_at DESC NULLS LAST"),
    Drill(key="needs_recruiter_review",
          label="Needs a recruiter",
          action=("INCOMPLETE or INSUFFICIENT_EVIDENCE is not a rejection. It "
                  "means the interview did not establish enough."),
          source="public.interview_scorecards sc",
          where=("sc.org_id = :o AND (sc.completeness_state = 'INCOMPLETE' "
                 "OR sc.overall_state = 'INSUFFICIENT_EVIDENCE')"),
          columns=("sc.id, sc.interview_id, sc.rubric_key, "
                   "sc.completeness_state, sc.overall_state, "
                   "sc.overall_score"),
          order_by="sc.overall_score NULLS FIRST"),
)}


def get(key: str) -> Optional[Drill]:
    return DRILLS.get(key)


def keys() -> List[str]:
    return sorted(DRILLS)
