"""Turn a delivered load into an invoice, a settlement, and a margin.

THE THREE REFUSALS
Everything here is arithmetic. What makes it worth writing down is what it
declines to do:

  1. NO INVOICE WITHOUT POD. `DELIVERED` is a driver tapping a button --
     an assertion by an interested party. Billing reads `proof_of_delivery`,
     which is a separate row with its own evidence strength. Invoicing off the
     status field is how a carrier bills for a load the receiver never got.

  2. NO UNAPPROVED ACCESSORIAL ON AN INVOICE. Detention happening and
     detention being billable are different facts. Only APPROVED accessorials
     reach a total, and the derivation note names each one.

  3. NO W-2 DRIVER PAID FROM HERE. A company driver's earnings are a payroll
     input, not a payable. The schema refuses the state and this module routes
     them to payroll, because mixing 1099 settlement with W-2 payroll for UI
     convenience is a misclassification finding waiting to happen.

MARGIN IS NOT REVENUE, AND SAYS SO
`load_margin` reports contribution margin and the AUTHORITY of every cost that
went into it. A modelled fuel figure and a fuel receipt are both useful and are
not the same fact, so the result carries the weakest authority present -- the
minimum, never the average -- and names which cost held it there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from app.trucking import rate_confirmation as RC

BILLING_VERSION = "billing-2026.08.29"

#: Ordered weakest to strongest. The grade of a margin is the weakest input.
AUTHORITY_ORDER = ("MODELED", "PLATFORM_REPORTED", "CORROBORATED",
                   "FINANCIAL_ACTUAL")

#: POD strengths that support invoicing. ASSERTED_BY_DRIVER does not: it is the
#: same claim as the DELIVERED status, recorded in a different table.
BILLABLE_POD_STRENGTH = ("RECEIVER_ACKNOWLEDGED", "SIGNED_DOCUMENT",
                         "EDI_CONFIRMED")


def money_str(cents: int) -> str:
    """Cents as a person reads them.

    THE NOTES ARE SHOWN TO CUSTOMERS AND CARRIERS.
    A derivation note is not a log line. It is printed under an invoice a
    shipper is disputing and under a settlement a carrier is questioning, and
    it read "linehaul 512500 from the contract rate on the load". Nobody
    outside this repository writes money that way, and a document that does
    tells its reader it was not written for them.
    """
    return f"${cents / 100:,.2f}"


class BillingRefused(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass
class InvoiceDraft:
    linehaul_cents: int
    accessorial_cents: int
    total_cents: int
    derivation_note: str
    accessorial_ids: List[object] = field(default_factory=list)


def build_invoice(*, load, pod, accessorials: Sequence) -> InvoiceDraft:
    """Derive an invoice. Never a typed total.

    `load` needs `.customer_rate_cents` and `.status`. `pod` may be None.
    Accessorials need `.state`, `.direction`, `.amount_cents`,
    `.accessorial_type` and `.id`.
    """
    if pod is None:
        raise BillingRefused(
            "POD_MISSING",
            "this load has no proof of delivery. A DELIVERED status is the "
            "driver's assertion; an invoice needs the receiver's.")

    strength = (getattr(pod, "evidence_strength", "") or "").upper()
    if strength not in BILLABLE_POD_STRENGTH:
        raise BillingRefused(
            "POD_TOO_WEAK",
            f"the proof of delivery is {strength or 'unrecorded'}. "
            f"ASSERTED_BY_DRIVER restates the status field rather than "
            f"corroborating it, so it cannot support billing.")

    linehaul = int(getattr(load, "customer_rate_cents", 0) or 0)
    if linehaul <= 0:
        raise BillingRefused(
            "NO_CONTRACT_RATE",
            "the load has no customer rate. An invoice derived from a missing "
            "rate would be a manual total wearing a contract's name.")

    billable = [a for a in accessorials
                if (getattr(a, "direction", "") or "") == "CUSTOMER_BILLABLE"
                and (getattr(a, "state", "") or "") == "APPROVED"]
    skipped = [a for a in accessorials
               if (getattr(a, "direction", "") or "") == "CUSTOMER_BILLABLE"
               and (getattr(a, "state", "") or "") != "APPROVED"]

    acc_total = sum(int(getattr(a, "amount_cents", 0) or 0) for a in billable)

    parts = [f"Linehaul {money_str(linehaul)} from the contract rate on the "
             f"load"]
    for a in billable:
        parts.append(
            f"{str(getattr(a, 'accessorial_type', 'accessorial')).replace('_', ' ').lower()} "
            f"{money_str(int(getattr(a, 'amount_cents', 0) or 0))} "
            f"(approved by {getattr(a, 'approved_by', None) or 'unknown'})")
    if skipped:
        parts.append(
            "excluded, not approved: "
            + ", ".join(f"{getattr(a, 'accessorial_type', '?')}"
                        f"[{getattr(a, 'state', '?')}]" for a in skipped))
    parts.append(f"released by a {strength.replace('_', ' ').lower()} "
                 f"proof of delivery")

    return InvoiceDraft(
        linehaul_cents=linehaul,
        accessorial_cents=acc_total,
        total_cents=linehaul + acc_total,
        derivation_note="; ".join(parts),
        accessorial_ids=[getattr(a, "id", None) for a in billable])


@dataclass
class SettlementDraft:
    payee_kind: str
    linehaul_cents: int
    accessorial_cents: int
    deduction_cents: int
    total_cents: int
    derivation_note: str
    #: True when this must go to payroll rather than be paid directly.
    routes_to_payroll: bool = False


def check_linehaul_against(load, ratecon) -> int:
    """What the settlement proposes to pay as linehaul.

    The load's own `carrier_rate_cents` when it is set -- a dispatcher may have
    recorded a different figure than the confirmation, and the whole point of
    the reconciliation is to notice. When it is unset the confirmation's own
    total is proposed, so a load that was never given a rate does not read as
    a proposal of zero and slip through as an underpayment note.
    """
    recorded = int(getattr(load, "carrier_rate_cents", 0) or 0)
    if recorded > 0:
        return recorded
    return (int(getattr(ratecon, "linehaul_cents", 0) or 0)
            + int(getattr(ratecon, "fuel_surcharge_cents", 0) or 0))


def build_settlement(*, load, driver=None, carrier=None,
                     accessorials: Sequence = (),
                     deductions_cents: int = 0,
                     ratecon=None) -> SettlementDraft:
    """What we owe for moving this load, and to whom, in what form.

    `ratecon` is REQUIRED for a brokered load. See the refusal below.
    """
    mode = (getattr(load, "fulfilment_mode", "") or "").upper()

    if mode == "BROKERED":
        if carrier is None:
            raise BillingRefused(
                "NO_CARRIER",
                "a brokered load has no carrier, so there is nobody to pay")

        # THE NOTE USED TO CITE A DOCUMENT THAT DID NOT EXIST.
        # This read `load.carrier_rate_cents` -- a number in a field -- and
        # wrote "carrier rate {rate} from the rate confirmation". The most
        # expensive kind of wrong thing to say, because it is checkable and the
        # person checking is the one being paid.
        #
        # A brokered payable is now derived FROM the accepted confirmation and
        # reconciled against it. The refusals below are `rate_confirmation`'s,
        # re-raised as billing refusals so the caller sees one failure mode.
        if ratecon is None:
            raise BillingRefused(
                "NO_RATE_CONFIRMATION",
                "this brokered load has no rate confirmation, so there is no "
                "document a carrier payable can be defended against. Paying "
                "an amount nobody agreed to is the failure this refusal "
                "exists to prevent.")

        payable = [a for a in accessorials
                   if (getattr(a, "direction", "") or "") == "CARRIER_PAYABLE"]
        check = RC.check_payable(
            ratecon=ratecon,
            proposed_linehaul_cents=check_linehaul_against(load, ratecon),
            accessorials=payable)
        if not check.ok:
            raise BillingRefused(
                check.refusal_codes[0],
                " ".join(check.notes)
                or "; ".join(v.detail for v in check.accessorials
                             if not v.payable))

        rate = check.authorised_linehaul_cents
        acc = check.authorised_accessorial_cents
        if rate <= 0:
            raise BillingRefused(
                "NO_CARRIER_RATE",
                "the rate confirmation agrees a total of zero")

        return SettlementDraft(
            payee_kind="CARRIER",
            linehaul_cents=rate, accessorial_cents=acc,
            deduction_cents=deductions_cents,
            total_cents=rate + acc - deductions_cents,
            derivation_note=(
                RC.derivation_note(ratecon=ratecon, check=check)
                + (f"; less {money_str(deductions_cents)} of deductions"
                   if deductions_cents else "")))

    if driver is None:
        raise BillingRefused(
            "NO_DRIVER",
            "an own-fleet load has no driver assigned")

    classification = (getattr(driver, "worker_classification", "")
                      or "W2_EMPLOYEE").upper()
    pay_model = (getattr(driver, "pay_model", "") or "HOURLY").upper()
    rate = int(getattr(driver, "pay_rate_cents", 0) or 0)
    miles = int(getattr(load, "miles", 0) or 0)

    if pay_model == "PER_MILE":
        gross = rate * miles
        basis = f"{miles} miles at {rate} per mile"
    elif pay_model == "PER_LOAD":
        gross = rate
        basis = "flat per-load rate"
    elif pay_model == "PERCENTAGE":
        gross = int(int(getattr(load, "customer_rate_cents", 0) or 0)
                    * (rate / 10_000))
        basis = f"{rate / 100:.2f}% of the customer rate"
    else:
        gross = rate
        basis = f"{pay_model.lower()} rate"

    payable = [a for a in accessorials
               if (getattr(a, "direction", "") or "") == "CARRIER_PAYABLE"
               and (getattr(a, "state", "") or "") == "APPROVED"]
    acc = sum(int(getattr(a, "amount_cents", 0) or 0) for a in payable)

    if classification == "W2_EMPLOYEE":
        # Routed, not paid. The amount becomes a payroll input so that tax
        # withholding, employer contributions and the payroll controls all
        # apply to it -- none of which happen if it is paid as an invoice.
        return SettlementDraft(
            payee_kind="DRIVER_W2",
            linehaul_cents=gross, accessorial_cents=acc,
            deduction_cents=0, total_cents=gross + acc,
            routes_to_payroll=True,
            derivation_note=(
                f"{basis}; {len(payable)} approved accessorial(s) "
                f"{money_str(acc)}. "
                f"This driver is W2_EMPLOYEE, so the amount is a PAYROLL "
                f"INPUT and must not be paid from settlement -- withholding "
                f"and employer contributions apply to it."))

    return SettlementDraft(
        payee_kind="DRIVER_CONTRACTOR",
        linehaul_cents=gross, accessorial_cents=acc,
        deduction_cents=deductions_cents,
        total_cents=gross + acc - deductions_cents,
        derivation_note=(
            f"{basis}; {len(payable)} approved accessorial(s) "
            f"{money_str(acc)}; deductions {money_str(deductions_cents)}. "
            f"Classification "
            f"{classification} — settled directly, not through payroll."))


@dataclass
class Margin:
    revenue_cents: int
    accessorial_revenue_cents: int
    direct_cost_cents: int
    contribution_margin_cents: int
    margin_pct: Optional[float]
    #: The WEAKEST authority among the costs. Never an average.
    cost_authority: str
    limiting_cost: Optional[str]
    cost_breakdown: Dict[str, int] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "revenue_cents": self.revenue_cents,
            "accessorial_revenue_cents": self.accessorial_revenue_cents,
            "direct_cost_cents": self.direct_cost_cents,
            "contribution_margin_cents": self.contribution_margin_cents,
            "margin_pct": self.margin_pct,
            "cost_authority": self.cost_authority,
            "limiting_cost": self.limiting_cost,
            "cost_breakdown": self.cost_breakdown,
            "note": self.note,
        }


def load_margin(*, invoice, costs: Sequence) -> Margin:
    """Contribution margin for one load, graded by its weakest cost.

    This is CONTRIBUTION margin: revenue less the direct costs of moving this
    freight. It is not profit -- no overhead, no depreciation, no G&A -- and
    the note says so, because "margin" printed next to a big number is read as
    profit by everyone who is not an accountant.
    """
    linehaul = int(getattr(invoice, "linehaul_cents", 0) or 0)
    acc_rev = int(getattr(invoice, "accessorial_cents", 0) or 0)
    revenue = linehaul + acc_rev

    breakdown: Dict[str, int] = {}
    weakest_idx = len(AUTHORITY_ORDER) - 1
    limiting: Optional[str] = None

    for c in costs:
        ctype = getattr(c, "cost_type", "OTHER")
        amount = int(getattr(c, "amount_cents", 0) or 0)
        breakdown[ctype] = breakdown.get(ctype, 0) + amount

        auth = (getattr(c, "authority", "") or "MODELED").upper()
        idx = AUTHORITY_ORDER.index(auth) if auth in AUTHORITY_ORDER else 0
        if idx < weakest_idx:
            weakest_idx = idx
            limiting = ctype

    direct = sum(breakdown.values())
    contribution = revenue - direct

    if not costs:
        authority = "MODELED"
        note = ("No direct costs are recorded for this load, so the figure "
                "shown is revenue, not margin.")
        limiting = None
    else:
        authority = AUTHORITY_ORDER[weakest_idx]
        note = (
            f"Contribution margin: revenue less direct costs of moving this "
            f"load. Not profit -- no overhead, depreciation or G&A. The grade "
            f"is the WEAKEST cost authority present ({authority}"
            + (f", held there by {limiting}" if limiting else "") + "), "
            f"because averaging authorities would let one receipt make a "
            f"page of estimates look measured.")

    return Margin(
        revenue_cents=revenue,
        accessorial_revenue_cents=acc_rev,
        direct_cost_cents=direct,
        contribution_margin_cents=contribution,
        margin_pct=(round(100.0 * contribution / revenue, 2)
                    if revenue else None),
        cost_authority=authority,
        limiting_cost=limiting,
        cost_breakdown=breakdown,
        note=note)


# ---------------------------------------------------------------------------
# Modeled margin versus realised margin
# ---------------------------------------------------------------------------

@dataclass
class MarginPair:
    """Two margins for the same load, and the gap between them.

    WHY BOTH
    A contribution margin computed from an invoice and a set of cost rows is
    what we EXPECT to have made. It is useful the day the load delivers and it
    is not the same statement as "we made this".

    Realised margin only counts money that actually moved: cash collected
    against the invoice, and costs whose authority is FINANCIAL_ACTUAL. A
    modelled fuel allocation is a good estimate and it is not a payment.

    Showing one number and calling it margin is the overclaim this exists to
    prevent. Showing both, with the variance, is the thing a CFO can act on --
    a large negative variance means the estimate was wrong or the cash has not
    arrived, and those need different responses.
    """

    modeled: "Margin"
    realised_revenue_cents: int
    realised_cost_cents: int
    realised_margin_cents: Optional[int]
    realised_state: str            # REALISED | AWAITING_CASH | AWAITING_COSTS | NONE
    variance_cents: Optional[int]
    cash_collected_cents: int
    actual_cost_cents: int
    modeled_cost_cents: int
    note: str

    def as_dict(self) -> dict:
        return {
            "modeled": self.modeled.as_dict(),
            "realised": {
                "state": self.realised_state,
                "revenue_cents": self.realised_revenue_cents,
                "cost_cents": self.realised_cost_cents,
                "margin_cents": self.realised_margin_cents,
                "cash_collected_cents": self.cash_collected_cents,
                "actual_cost_cents": self.actual_cost_cents,
                "modeled_cost_cents": self.modeled_cost_cents,
            },
            "variance_cents": self.variance_cents,
            "note": self.note,
        }


def margin_pair(*, invoice, costs: Sequence,
                cash_collected_cents: int = 0) -> MarginPair:
    """Both margins, and what separates them.

    `invoice` needs .linehaul_cents, .accessorial_cents and optionally
    .paid_cents. Costs need .amount_cents and .authority.
    """
    modeled = load_margin(invoice=invoice, costs=costs)

    collected = int(cash_collected_cents
                    or getattr(invoice, "paid_cents", 0) or 0)

    actual = sum(int(getattr(c, "amount_cents", 0) or 0) for c in costs
                 if (getattr(c, "authority", "") or "").upper()
                 == "FINANCIAL_ACTUAL")
    modelled_only = modeled.direct_cost_cents - actual

    if collected <= 0 and actual <= 0:
        state = "NONE"
        realised = None
        note = ("Nothing has been realised: no cash collected and no cost with "
                "FINANCIAL_ACTUAL authority. The modelled figure is an "
                "expectation, not a result.")
    elif collected <= 0:
        state = "AWAITING_CASH"
        realised = None
        note = (f"{money_str(actual)} of cost is real but no cash has been "
                f"collected, so there is no realised margin yet. A delivered, "
                f"invoiced, unpaid load has spent money and earned a "
                f"receivable.")
    elif actual <= 0:
        state = "AWAITING_COSTS"
        realised = None
        note = (f"{money_str(collected)} was collected but no cost carries "
                f"FINANCIAL_ACTUAL authority, so a realised margin would be "
                f"revenue with estimated costs subtracted -- which is the "
                f"modelled figure wearing a stronger label.")
    else:
        state = "REALISED"
        realised = collected - actual
        note = (f"Realised from {money_str(collected)} collected and "
                f"{money_str(actual)} of FINANCIAL_ACTUAL cost. "
                + (f"{money_str(modelled_only)} of modelled cost is EXCLUDED "
                   f"from this figure and included in the modelled one."
                   if modelled_only else
                   "Every cost on this load is a real payment."))

    variance = (realised - modeled.contribution_margin_cents
                if realised is not None else None)

    return MarginPair(
        modeled=modeled,
        realised_revenue_cents=collected,
        realised_cost_cents=actual,
        realised_margin_cents=realised,
        realised_state=state,
        variance_cents=variance,
        cash_collected_cents=collected,
        actual_cost_cents=actual,
        modeled_cost_cents=modelled_only,
        note=note)


