"""From a name on a list to a dollar of margin, with the refusals in between.

WHAT THIS ANSWERS
"Did the thing we did produce any money?" -- which almost every tool in this
category either skips or answers with a funnel chart. A funnel counts stages.
This counts dollars, and says which of them actually moved.

THE THREE REFUSALS, AND WHY EACH ONE MATTERS MORE THAN THE FEATURE IT BLOCKS

  1. A SOURCE THAT DOES NOT LICENCE OUTREACH CANNOT BE MARKETED TO.
     FMCSA publishes a register of carriers. Being able to read it is not
     permission to run a campaign against the businesses in it, and the fact
     that the data is public is exactly what makes the mistake easy. The
     licence travels with the prospect and `check_action` refuses before the
     spend is recorded, not after.

     The register is still useful -- it is how a broker builds a CARRIER
     network, which is what a public carrier register legitimately supports.
     The refusal is about outreach, not about reading.

  2. NOTHING AUTO-CREATES A LEAD.
     A scan can surface a name. Only a person can decide it is worth pursuing.
     Without that gate, "our system found 400 leads" means "our system copied
     400 rows", and every downstream number inherits the exaggeration.

  3. ATTRIBUTION IS GRADED, AND CASH IS WHAT MAKES IT REALISED.
     A margin computed from an invoice and a set of cost rows is what we expect
     to have made. It is not the same statement as "this campaign made us
     money". The grade is the MINIMUM authority across the spend and the
     costs -- never the average, because one paid invoice does not make a page
     of estimates measured.

WHAT IT DELIBERATELY DOES NOT CLAIM
Causation. One customer arriving after one campaign is a sequence. The verdict
says what the economics were, and the note says that is not the same as proof
that the campaign caused them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence

LOOP_VERSION = "commercial-loop-2026.08.30"

# --- stages ----------------------------------------------------------------
OBSERVED = "OBSERVED"
SAVED = "SAVED"
CONTACTED = "CONTACTED"
QUALIFIED = "QUALIFIED"
CUSTOMER = "CUSTOMER"
DISQUALIFIED = "DISQUALIFIED"

STAGES = (OBSERVED, SAVED, CONTACTED, QUALIFIED, CUSTOMER, DISQUALIFIED)

#: A stage may advance to these. Nothing goes backwards except to
#: DISQUALIFIED, which is always allowed -- a deal can die at any point.
_NEXT: Dict[str, tuple] = {
    OBSERVED: (SAVED, DISQUALIFIED),
    SAVED: (CONTACTED, QUALIFIED, DISQUALIFIED),
    CONTACTED: (QUALIFIED, DISQUALIFIED),
    QUALIFIED: (CUSTOMER, DISQUALIFIED),
    CUSTOMER: (DISQUALIFIED,),
    DISQUALIFIED: (),
}

#: Ordered weakest to strongest, exactly as the trucking cost ladder is.
AUTHORITY_ORDER = ("MODELED", "PLATFORM_REPORTED", "CORROBORATED",
                   "FINANCIAL_ACTUAL")

WORKED = "WORKED"
DID_NOT_WORK = "DID_NOT_WORK"
TOO_EARLY = "TOO_EARLY"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

REALISED = "REALISED"
MODELED = "MODELED"


class LoopRefused(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# ---------------------------------------------------------------------------
# 1. The rights gate
# ---------------------------------------------------------------------------

@dataclass
class MarketingDecision:
    allowed: bool
    refusal_code: Optional[str] = None
    reason: str = ""
    #: What the source IS good for, when it is not good for outreach.
    alternative: str = ""


def check_marketing_allowed(*, source) -> MarketingDecision:
    """May we run an outbound action against a prospect from this source?

    The kind is not the test -- the LICENCE is. A public register that happens
    to carry an outreach licence would pass; a purchased list whose licence has
    lapsed would not.
    """
    permits = bool(getattr(source, "permits_direct_marketing", False))
    kind = (getattr(source, "kind", "") or "UNATTRIBUTED").upper()
    name = getattr(source, "name", None) or "this source"

    if permits:
        return MarketingDecision(allowed=True,
                                 reason=getattr(source, "licence_note", "") or "")

    if kind == "PUBLIC_REGISTER":
        return MarketingDecision(
            allowed=False,
            refusal_code="SOURCE_DOES_NOT_LICENCE_OUTREACH",
            reason=(f"{name} is a public register. Being able to read it is "
                    f"not permission to run a campaign against the businesses "
                    f"in it, and the fact that it is public is what makes that "
                    f"mistake easy."),
            alternative=("A carrier register is how a brokerage builds its "
                         "CARRIER network. That use is what the register "
                         "actually supports."))

    return MarketingDecision(
        allowed=False,
        refusal_code="SOURCE_DOES_NOT_LICENCE_OUTREACH",
        reason=(f"{name} carries no licence permitting direct marketing. "
                f"Record the basis on the source before spending against it."),
        alternative=("A prospect the sales team sourced themselves needs no "
                     "third-party licence."))


# ---------------------------------------------------------------------------
# 2. The human gate
# ---------------------------------------------------------------------------

def check_stage_change(*, current: str, target: str,
                       saved_by: Optional[str]) -> None:
    """Advance a prospect, or refuse to.

    Raises rather than returning a decision, because every caller here is
    performing a write and there is nothing sensible to do with a "no" except
    stop.
    """
    cur = (current or "").upper()
    tgt = (target or "").upper()
    if cur not in STAGES or tgt not in STAGES:
        raise LoopRefused("UNKNOWN_STAGE",
                          f"{current!r} -> {target!r} is not a stage change")
    if tgt not in _NEXT[cur]:
        allowed = _NEXT[cur]
        raise LoopRefused(
            "ILLEGAL_STAGE_CHANGE",
            (f"a {cur} prospect cannot become {tgt}. "
             + (f"From {cur} it may become {', '.join(allowed)}."
                if allowed else f"{cur} is terminal.")))
    if tgt != OBSERVED and not (saved_by or "").strip():
        raise LoopRefused(
            "NO_HUMAN_SAVED_THIS",
            ("a scan can surface a name; a person decides it is worth "
             "pursuing. Without that, 'the system found 400 leads' means "
             "'the system copied 400 rows'."))


def check_action(*, source, prospect_stage: str) -> None:
    """May this action be recorded against this prospect?"""
    d = check_marketing_allowed(source=source)
    if not d.allowed:
        raise LoopRefused(d.refusal_code or "SOURCE_DOES_NOT_LICENCE_OUTREACH",
                          f"{d.reason} {d.alternative}".strip())
    if (prospect_stage or "").upper() == OBSERVED:
        raise LoopRefused(
            "NO_HUMAN_SAVED_THIS",
            ("this prospect has only been observed. Spending against a row "
             "nobody chose is how a pipeline fills with names."))


# ---------------------------------------------------------------------------
# 3. Attribution
# ---------------------------------------------------------------------------

@dataclass
class Attribution:
    verdict: str
    grade: str
    basis: str
    spend_cents: int
    revenue_cents: int
    direct_cost_cents: int
    contribution_margin_cents: int
    cash_collected_cents: int
    loads_count: int
    net_cents: int
    margin_per_dollar: Optional[float]
    note: str
    limiting_input: Optional[str] = None
    caveats: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict, "grade": self.grade, "basis": self.basis,
            "spend_cents": self.spend_cents,
            "revenue_cents": self.revenue_cents,
            "direct_cost_cents": self.direct_cost_cents,
            "contribution_margin_cents": self.contribution_margin_cents,
            "cash_collected_cents": self.cash_collected_cents,
            "loads_count": self.loads_count,
            "net_cents": self.net_cents,
            "margin_per_dollar": self.margin_per_dollar,
            "note": self.note,
            "limiting_input": self.limiting_input,
            "caveats": self.caveats,
        }


def _weakest(pairs: Sequence[tuple]) -> tuple:
    """The lowest authority present, and what held it there."""
    worst_i, worst_label = len(AUTHORITY_ORDER) - 1, None
    for label, authority in pairs:
        try:
            i = AUTHORITY_ORDER.index((authority or "MODELED").upper())
        except ValueError:
            i = 0
        if i < worst_i:
            worst_i, worst_label = i, label
    return AUTHORITY_ORDER[worst_i], worst_label


def attribute(*, actions: Sequence, invoices: Sequence,
              costs: Sequence, loads_count: int = 0) -> Attribution:
    """What this prospect cost, what it produced, and how sure we are.

    `actions` need .spend_cents and .spend_authority.
    `invoices` need .total_cents and .paid_cents.
    `costs` need .amount_cents and .authority.
    """
    spend = sum(int(getattr(a, "spend_cents", 0) or 0) for a in actions)
    revenue = sum(int(getattr(i, "total_cents", 0) or 0) for i in invoices)
    collected = sum(int(getattr(i, "paid_cents", 0) or 0) for i in invoices)
    direct = sum(int(getattr(c, "amount_cents", 0) or 0) for c in costs)
    margin = revenue - direct
    net = margin - spend

    graded = [(f"{getattr(a, 'action_kind', 'spend')} spend",
               getattr(a, "spend_authority", "MODELED")) for a in actions]
    graded += [(f"{getattr(c, 'cost_type', 'cost')} cost",
                getattr(c, "authority", "MODELED")) for c in costs]
    grade, limiting = _weakest(graded) if graded else ("MODELED", None)

    caveats = [
        ("One customer arriving after one action is a sequence, not a "
         "controlled experiment. This is the economics of what happened, not "
         "proof of what caused it."),
    ]

    # THE CASH GATE.
    basis = REALISED if collected > 0 else MODELED
    if collected > 0 and collected < revenue:
        caveats.append(
            f"{money(collected)} of {money(revenue)} invoiced has been "
            f"collected. The rest is a receivable, not a result.")
    if basis == MODELED:
        caveats.append(
            "No cash has been collected against these invoices, so nothing "
            "here has been realised.")

    if not actions:
        verdict = INSUFFICIENT_EVIDENCE
        note = ("no action has been recorded against this prospect, so there "
                "is nothing to attribute an outcome to")
    elif not invoices:
        verdict = TOO_EARLY
        note = (f"{money(spend)} spent and nothing invoiced yet. That is not "
                f"a failure; it is a question that cannot be answered yet.")
    elif net > 0:
        verdict = WORKED
        note = (f"{money(margin)} of contribution margin against "
                f"{money(spend)} of spend — {money(net)} net.")
    else:
        verdict = DID_NOT_WORK
        note = (f"{money(margin)} of contribution margin against "
                f"{money(spend)} of spend — {money(net)} net. "
                f"That is the arithmetic, not a judgement about the channel.")

    if limiting:
        note += f" Graded {grade}, held there by the {limiting}."

    return Attribution(
        verdict=verdict, grade=grade, basis=basis,
        spend_cents=spend, revenue_cents=revenue,
        direct_cost_cents=direct, contribution_margin_cents=margin,
        cash_collected_cents=collected, loads_count=loads_count,
        net_cents=net,
        margin_per_dollar=(round(margin / spend, 2) if spend else None),
        note=note, limiting_input=limiting, caveats=caveats)
