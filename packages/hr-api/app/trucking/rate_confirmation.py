"""The rate confirmation, and what a carrier's pay is defensible against.

THE HOLE THIS FILLS
`build_settlement` read `load.carrier_rate_cents` and wrote the derivation note
"carrier rate {rate} from the rate confirmation". There was no rate
confirmation. The note told a carrier the figure came from a document that did
not exist, which is the most expensive kind of wrong thing to say: it is
checkable, and the person checking is the one being paid.

WHAT AN ACCEPTED CONFIRMATION ESTABLISHES
That THIS carrier agreed to THIS linehaul and THIS fuel surcharge for THIS
load, at a recorded time, through a recorded channel, and that the document
they were sent hashes to what we hold. It also fixes which accessorials were
pre-approved and on what terms -- free time, rate, unit and cap.

WHAT IT DOES NOT ESTABLISH
That the carrier may legally haul. Authority and insurance are
`eligibility.check_carrier`, and a signed confirmation from a revoked carrier
is a signed document from a carrier who may not move the freight. The two
controls are independent and both apply.

THE THREE REFUSALS
  1. A BROKERED LOAD DOES NOT DISPATCH without an ACCEPTED confirmation.
     Tendering freight on a rate nobody agreed to is how a broker discovers
     the rate at settlement time, from the carrier.

  2. A CARRIER PAYABLE MAY NOT EXCEED what the confirmation authorises.
     Linehaul comes from the document; accessorials must each be pre-approved
     by kind AND within their agreed cap. An accessorial that is not in the
     document is not automatically refused -- it needs a separate human
     approval, which is the existing EVENT-vs-CHARGE distinction.

  3. AN ACCEPTED CONFIRMATION IS NOT EDITED. It is superseded by an amendment
     that names it and says why, because a settlement already citing the
     original still has to be defensible.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

RATECON_VERSION = "ratecon-2026.08.30"

DRAFT = "DRAFT"
ISSUED = "ISSUED"
ACCEPTED = "ACCEPTED"
DECLINED = "DECLINED"
SUPERSEDED = "SUPERSEDED"
VOID = "VOID"

STATES = (DRAFT, ISSUED, ACCEPTED, DECLINED, SUPERSEDED, VOID)

#: Only these transitions happen. Anything else is a bug or an attempt to
#: rewrite history, and both should raise rather than be tolerated.
_TRANSITIONS: Dict[str, tuple] = {
    DRAFT: (ISSUED, VOID),
    ISSUED: (ACCEPTED, DECLINED, VOID),
    ACCEPTED: (SUPERSEDED,),
    DECLINED: (VOID,),
    SUPERSEDED: (),
    VOID: (),
}

#: Statuses at which the freight has not yet been tendered to the carrier.
_PRE_DISPATCH = ("DRAFT", "QUOTED", "BOOKED", "PLANNED")

#: How a pre-approved accessorial is measured.
UNITS = ("HOUR", "DAY", "STOP", "MILE", "FLAT", "PERCENT")


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


class RateConRefused(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


# ---------------------------------------------------------------------------
# Pre-approved accessorial terms
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AccessorialTerm:
    """One accessorial the broker committed to in advance.

    `free_time_minutes` is why this is a structure and not a number. "Detention
    at $50/hour" and "detention at $50/hour after two hours free" are different
    agreements, and the second is the one the industry actually writes down.
    """
    kind: str
    rate_cents: int
    unit: str = "FLAT"
    free_time_minutes: int = 0
    cap_cents: Optional[int] = None

    @classmethod
    def parse(cls, raw: dict) -> "AccessorialTerm":
        kind = str(raw.get("kind") or "").strip().upper()
        if not kind:
            raise RateConRefused("TERM_WITHOUT_KIND",
                                 "an accessorial term names no accessorial")
        unit = str(raw.get("unit") or "FLAT").strip().upper()
        if unit not in UNITS:
            raise RateConRefused(
                "UNKNOWN_ACCESSORIAL_UNIT",
                f"{unit!r} is not one of {list(UNITS)}")
        rate = int(raw.get("rate_cents") or 0)
        if rate < 0:
            raise RateConRefused("NEGATIVE_TERM_RATE",
                                 f"{kind} is agreed at a negative rate")
        cap = raw.get("cap_cents")
        return cls(kind=kind, rate_cents=rate, unit=unit,
                   free_time_minutes=int(raw.get("free_time_minutes") or 0),
                   cap_cents=None if cap is None else int(cap))

    def as_dict(self) -> dict:
        return {"kind": self.kind, "rate_cents": self.rate_cents,
                "unit": self.unit, "free_time_minutes": self.free_time_minutes,
                "cap_cents": self.cap_cents}


def parse_terms(raw: Optional[Sequence]) -> List[AccessorialTerm]:
    terms = [AccessorialTerm.parse(dict(r)) for r in (raw or [])]
    seen = set()
    for t in terms:
        if t.kind in seen:
            raise RateConRefused(
                "DUPLICATE_ACCESSORIAL_TERM",
                f"{t.kind} is agreed twice at different terms; the document "
                f"says two things about the same charge")
        seen.add(t.kind)
    return terms


def term_for(terms: Sequence[AccessorialTerm],
             kind: str) -> Optional[AccessorialTerm]:
    want = (kind or "").strip().upper()
    for t in terms:
        if t.kind == want:
            return t
    return None


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

def render_document(*, confirmation_number: str, carrier_name: str,
                    load_number: str, origin: str, destination: str,
                    linehaul_cents: int, fuel_surcharge_cents: int,
                    terms: Sequence[AccessorialTerm],
                    equipment: str = "", commodity: str = "") -> str:
    """The text that is sent, and whose hash is recorded.

    Plain text on purpose. The hash has to be over what the carrier actually
    read; hashing a JSON blob that a renderer later turns into something else
    proves the blob was not edited, not that the terms were not.
    """
    lines = [
        f"RATE CONFIRMATION {confirmation_number}",
        f"Carrier: {carrier_name}",
        f"Load: {load_number}   {origin} -> {destination}",
    ]
    if equipment:
        lines.append(f"Equipment: {equipment}")
    if commodity:
        lines.append(f"Commodity: {commodity}")
    lines += [
        "",
        f"Linehaul: {linehaul_cents / 100:,.2f} USD",
        f"Fuel surcharge: {fuel_surcharge_cents / 100:,.2f} USD",
        f"TOTAL: {(linehaul_cents + fuel_surcharge_cents) / 100:,.2f} USD",
        "",
        "Pre-approved accessorials:",
    ]
    if not terms:
        lines.append("  none. Any accessorial requires separate approval.")
    for t in terms:
        bit = f"  {t.kind}: {t.rate_cents / 100:,.2f} per {t.unit.lower()}"
        if t.free_time_minutes:
            bit += f", after {t.free_time_minutes} minutes free"
        if t.cap_cents is not None:
            bit += f", capped at {t.cap_cents / 100:,.2f}"
        lines.append(bit)
    lines += [
        "",
        "Accepting this confirmation binds the rate above for this load only.",
        "An accessorial not listed here is not pre-approved and requires "
        "separate written approval before it is payable.",
    ]
    return "\n".join(lines) + "\n"


def document_hash(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


@dataclass
class IntegrityResult:
    intact: bool
    code: str
    detail: str
    recorded_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None


def verify_document(*, document: Optional[str],
                    recorded_sha256: Optional[str]) -> IntegrityResult:
    """Does the document we hold still hash to what was accepted?

    A settlement may cite this confirmation months later. "The terms on file
    today" and "the terms the carrier accepted" are not the same claim unless
    something re-reads and compares -- the same property `pod.verify_document`
    exists for, and for the same reason.
    """
    if not recorded_sha256:
        return IntegrityResult(
            False, "NO_RECORDED_HASH",
            "no hash was recorded when this confirmation was issued, so "
            "nothing can be compared against it")
    if document is None:
        return IntegrityResult(
            False, "DOCUMENT_MISSING",
            "the row records a hash but the document itself is not available",
            recorded_sha256=recorded_sha256)
    actual = document_hash(document)
    if actual != recorded_sha256:
        return IntegrityResult(
            False, "DOCUMENT_ALTERED",
            ("the confirmation on file does not match the hash recorded when "
             "the carrier accepted it. A settlement citing these terms is "
             "citing a different document than the one that was agreed."),
            recorded_sha256=recorded_sha256, actual_sha256=actual)
    return IntegrityResult(True, "INTACT",
                           "the document matches the hash recorded at "
                           "acceptance",
                           recorded_sha256=recorded_sha256,
                           actual_sha256=actual)


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------

def validate_transition(current: str, target: str) -> None:
    cur = (current or "").upper()
    tgt = (target or "").upper()
    if cur not in STATES:
        raise RateConRefused("UNKNOWN_STATE", f"{current!r} is not a state")
    if tgt not in STATES:
        raise RateConRefused("UNKNOWN_STATE", f"{target!r} is not a state")
    if tgt not in _TRANSITIONS[cur]:
        allowed = _TRANSITIONS[cur]
        raise RateConRefused(
            "ILLEGAL_TRANSITION",
            (f"a {cur} rate confirmation cannot become {tgt}. "
             + (f"From {cur} it may only become {', '.join(allowed)}."
                if allowed
                else f"{cur} is terminal: amend it instead of changing it.")))


def validate_amendment(*, original_state: str,
                       reason: Optional[str]) -> None:
    """An accepted confirmation is superseded, never edited."""
    if (original_state or "").upper() != ACCEPTED:
        raise RateConRefused(
            "NOTHING_TO_AMEND",
            f"only an ACCEPTED confirmation is amended; this one is "
            f"{original_state}. Void it and issue a new one.")
    if not (reason or "").strip():
        raise RateConRefused(
            "AMENDMENT_WITHOUT_REASON",
            "an amendment changes what an existing settlement cites, so it "
            "records why")


# ---------------------------------------------------------------------------
# Refusal 1: dispatch
# ---------------------------------------------------------------------------

@dataclass
class DispatchDecision:
    allowed: bool
    refusal_codes: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def refuse(self, code: str, why: str) -> None:
        self.allowed = False
        self.refusal_codes.append(code)
        self.reasons.append(why)


def check_dispatch(*, load, ratecon=None) -> DispatchDecision:
    """May this load be tendered to the carrier?

    Own-fleet loads are unaffected: there is no counterparty to agree a rate
    with, and `eligibility.check_driver` is that flow's gate.
    """
    d = DispatchDecision(allowed=True)
    mode = (getattr(load, "fulfilment_mode", "") or "").upper()
    if mode != "BROKERED":
        return d

    if ratecon is None:
        d.refuse("NO_RATE_CONFIRMATION",
                 "this brokered load has no rate confirmation. Tendering "
                 "freight on a rate nobody agreed to means discovering the "
                 "rate at settlement time, from the carrier.")
        return d

    state = (getattr(ratecon, "state", "") or "").upper()
    if state != ACCEPTED:
        d.refuse("RATE_CONFIRMATION_NOT_ACCEPTED",
                 f"the rate confirmation is {state}. Only an ACCEPTED "
                 f"confirmation authorises a tender.")

    if str(getattr(ratecon, "load_id", "")) != str(getattr(load, "id", "")):
        d.refuse("RATE_CONFIRMATION_WRONG_LOAD",
                 "this confirmation was agreed for a different load")

    rc_carrier = getattr(ratecon, "carrier_id", None)
    load_carrier = getattr(load, "carrier_id", None)
    if load_carrier is not None and rc_carrier is not None \
            and str(rc_carrier) != str(load_carrier):
        d.refuse("RATE_CONFIRMATION_WRONG_CARRIER",
                 "the confirmation was agreed with a different carrier than "
                 "the one the load is assigned to")

    if int(getattr(ratecon, "agreed_total_cents", 0) or 0) <= 0:
        d.refuse("RATE_CONFIRMATION_HAS_NO_RATE",
                 "the confirmation agrees a total of zero")

    return d


# ---------------------------------------------------------------------------
# Refusal 2: the payable
# ---------------------------------------------------------------------------

@dataclass
class AccessorialVerdict:
    kind: str
    amount_cents: int
    payable: bool
    code: str
    detail: str


@dataclass
class PayableCheck:
    ok: bool
    authorised_linehaul_cents: int
    authorised_accessorial_cents: int
    authorised_total_cents: int
    accessorials: List[AccessorialVerdict] = field(default_factory=list)
    refusal_codes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def check_payable(*, ratecon, proposed_linehaul_cents: int,
                  accessorials: Sequence = ()) -> PayableCheck:
    """What the confirmation authorises paying, against what is proposed.

    Accessorials are judged one at a time so the answer is specific. "The
    settlement is too high" tells an ops person nothing; "DETENTION is $120
    over its agreed cap, and LUMPER is not in the confirmation at all" tells
    them exactly which two calls to make.
    """
    state = (getattr(ratecon, "state", "") or "").upper()
    agreed_linehaul = int(getattr(ratecon, "linehaul_cents", 0) or 0)
    agreed_fsc = int(getattr(ratecon, "fuel_surcharge_cents", 0) or 0)
    authorised_linehaul = agreed_linehaul + agreed_fsc

    check = PayableCheck(
        ok=True,
        authorised_linehaul_cents=authorised_linehaul,
        authorised_accessorial_cents=0,
        authorised_total_cents=authorised_linehaul)

    if state != ACCEPTED:
        check.ok = False
        check.refusal_codes.append("RATE_CONFIRMATION_NOT_ACCEPTED")
        check.notes.append(
            f"the confirmation is {state}; only an ACCEPTED one authorises a "
            f"payable")
        return check

    if proposed_linehaul_cents > authorised_linehaul:
        check.ok = False
        check.refusal_codes.append("LINEHAUL_EXCEEDS_CONFIRMATION")
        check.notes.append(
            f"the settlement proposes {proposed_linehaul_cents} of linehaul "
            f"and the confirmation agrees {authorised_linehaul}. Paying more "
            f"than was agreed is not generosity; it is an unreconciled "
            f"payable.")
    elif proposed_linehaul_cents < authorised_linehaul:
        # Not a refusal. Underpaying is a dispute the carrier will raise, and
        # the note is what an ops person needs to see before it becomes one.
        check.notes.append(
            f"the settlement proposes {proposed_linehaul_cents} against an "
            f"agreed {authorised_linehaul}. The carrier is owed the agreed "
            f"figure unless something was deducted for a reason.")

    terms = parse_terms(getattr(ratecon, "approved_accessorials", None))
    total_acc = 0
    for a in accessorials:
        kind = (getattr(a, "accessorial_kind", None)
                or getattr(a, "kind", "") or "").strip().upper()
        amount = int(getattr(a, "amount_cents", 0) or 0)
        a_state = (getattr(a, "state", "") or "").upper()

        if a_state != "APPROVED":
            check.accessorials.append(AccessorialVerdict(
                kind, amount, False, "ACCESSORIAL_NOT_APPROVED",
                f"{kind} is {a_state or 'unapproved'}. An accessorial "
                f"happening and an accessorial being payable are different "
                f"facts."))
            continue

        term = term_for(terms, kind)
        if term is None:
            # NOT a refusal of the settlement. A human approved it, which is
            # the separate control; it is flagged because it was not agreed in
            # advance and the carrier may cite the confirmation against it.
            total_acc += amount
            check.accessorials.append(AccessorialVerdict(
                kind, amount, True, "APPROVED_OUTSIDE_CONFIRMATION",
                f"{kind} is not pre-approved in the rate confirmation. It was "
                f"approved separately, so it is payable -- but the "
                f"confirmation does not support it if the carrier disputes "
                f"the amount."))
            continue

        if term.cap_cents is not None and amount > term.cap_cents:
            check.ok = False
            check.refusal_codes.append("ACCESSORIAL_OVER_CAP")
            check.accessorials.append(AccessorialVerdict(
                kind, amount, False, "ACCESSORIAL_OVER_CAP",
                f"{kind} is {amount} against an agreed cap of "
                f"{term.cap_cents}. The cap is the number both parties "
                f"signed."))
            continue

        total_acc += amount
        check.accessorials.append(AccessorialVerdict(
            kind, amount, True, "WITHIN_CONFIRMATION",
            f"{kind} is pre-approved at {term.rate_cents} per "
            f"{term.unit.lower()}"
            + (f" after {term.free_time_minutes} minutes free"
               if term.free_time_minutes else "")
            + (f", capped at {term.cap_cents}" if term.cap_cents is not None
               else "")))

    check.authorised_accessorial_cents = total_acc
    check.authorised_total_cents = authorised_linehaul + total_acc
    return check


def derivation_note(*, ratecon, check: PayableCheck) -> str:
    """What the settlement should say it was derived from.

    `build_settlement` used to write "carrier rate {rate} from the rate
    confirmation" while reading a field on the load. This says which document,
    by number, and what in it authorised each part.
    """
    number = getattr(ratecon, "confirmation_number", None) or "unnumbered"
    accepted = getattr(ratecon, "accepted_at", None)
    # A CARRIER READS THIS NOTE.
    # It used to render an ISO-8601 timestamp and raw cents --
    # "429000 ... at 2026-08-29T19:21:02.551194+00:00" -- under a settlement
    # someone is questioning. Both are correct and neither is written for the
    # person disputing the amount.
    if isinstance(accepted, datetime):
        when = accepted.strftime("%-d %B %Y at %H:%M UTC")
    elif accepted:
        when = str(accepted)
    else:
        when = "an unrecorded time"
    by = getattr(ratecon, "accepted_by", None) or "an unrecorded counterparty"
    bits = [
        f"Linehaul and fuel surcharge {_money(check.authorised_linehaul_cents)}"
        f" from rate confirmation {number}, accepted by {by} on {when}",
    ]
    inside = [v for v in check.accessorials
              if v.code == "WITHIN_CONFIRMATION"]
    outside = [v for v in check.accessorials
               if v.code == "APPROVED_OUTSIDE_CONFIRMATION"]
    if inside:
        bits.append(
            f"{len(inside)} pre-approved accessorial(s) "
            f"{_money(sum(v.amount_cents for v in inside))}")
    if outside:
        bits.append(
            f"{len(outside)} accessorial(s) "
            f"{_money(sum(v.amount_cents for v in outside))} approved "
            f"separately and NOT covered by the confirmation")
    return "; ".join(bits)
