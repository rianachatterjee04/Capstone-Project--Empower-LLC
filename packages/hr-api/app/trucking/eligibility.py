"""Whether this driver or carrier may be put on this load. Fails closed.

THE SHAPE OF THE CONTROL
Assignment asks a question with a legal answer, not a preference: does this
person hold the credentials this freight requires, unexpired, on the day it
moves? An expired medical card is not a warning to show a dispatcher who is
already behind. It is a refusal.

So `check_driver` returns a decision with reasons, and every uncertain input
resolves to NOT eligible:

    credential missing        -> refused
    credential expired        -> refused
    credential expiring before delivery -> refused (it expires mid-load)
    credential unverifiable   -> refused, with EXTERNAL_VERIFICATION_REQUIRED
    driver not ACTIVE         -> refused

WHY EXPIRING MID-LOAD IS A REFUSAL
A licence valid at dispatch and expired at delivery means the driver is
unlicensed on the road. Checking only "valid today" is the most common version
of this bug and it produces a violation that looks compliant in the log.

WHAT THIS IS NOT
It is not an ELD or hours-of-service system. Nothing here knows how long the
driver has been driving. `hos_state` is reported as NOT_CONNECTED so that a
dispatcher can see the gap rather than assume it was checked -- claiming an
HOS integration that does not exist is the kind of thing that gets a carrier
shut down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

ELIGIBILITY_VERSION = "eligibility-2026.08.29"

# Equipment -> the credentials it requires.
EQUIPMENT_REQUIREMENTS: Dict[str, tuple] = {
    "DRY_VAN": ("CDL_A", "MEDICAL_CARD"),
    "REEFER": ("CDL_A", "MEDICAL_CARD"),
    "FLATBED": ("CDL_A", "MEDICAL_CARD"),
    "TANKER": ("CDL_A", "MEDICAL_CARD", "TANKER"),
    "DOUBLES": ("CDL_A", "MEDICAL_CARD", "DOUBLES_TRIPLES"),
    "BOX_TRUCK": ("CDL_B", "MEDICAL_CARD"),
}

#: Verification states that may support a consequential assignment. A
#: self-reported CDL is a candidate's word; it is fine for a conversation and
#: not for putting someone behind 80,000 pounds.
ACCEPTABLE_VERIFICATION = ("DOCUMENT_ON_FILE", "VERIFIED_EXTERNAL")


@dataclass
class Reason:
    code: str
    detail: str
    credential_type: Optional[str] = None


@dataclass
class Decision:
    eligible: bool
    reasons: List[Reason] = field(default_factory=list)
    #: Things a dispatcher should see but which do not block.
    advisories: List[Reason] = field(default_factory=list)
    #: Integrations that would strengthen this answer and are not connected.
    not_connected: List[str] = field(default_factory=list)
    checked_version: str = ELIGIBILITY_VERSION

    @property
    def refusal_codes(self) -> List[str]:
        return [r.code for r in self.reasons]

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "reasons": [{"code": r.code, "detail": r.detail,
                         "credential_type": r.credential_type}
                        for r in self.reasons],
            "advisories": [{"code": r.code, "detail": r.detail,
                            "credential_type": r.credential_type}
                           for r in self.advisories],
            "not_connected": self.not_connected,
            "version": self.checked_version,
        }


def required_credentials(*, equipment: str, hazmat: bool = False) -> List[str]:
    """What this freight needs. Unknown equipment gets the strictest default.

    Defaulting an unrecognised equipment type to "no requirements" would mean a
    typo in a load record silently disables the control.
    """
    base = list(EQUIPMENT_REQUIREMENTS.get(
        (equipment or "").upper(), ("CDL_A", "MEDICAL_CARD")))
    if hazmat and "HAZMAT" not in base:
        base.append("HAZMAT")
    return base


def check_driver(*, driver, credentials: Sequence, equipment: str,
                 hazmat: bool = False, as_of: Optional[date] = None,
                 delivery_by: Optional[date] = None) -> Decision:
    """May this driver take this load?

    `driver` needs `.status` and `.worker_classification`. Each credential
    needs `.credential_type`, `.expires_on` and `.verification_state`.
    """
    as_of = as_of or date.today()
    d = Decision(eligible=True)

    # Hours of service is a real requirement this system cannot answer.
    d.not_connected.append("ELD_HOS")

    status = (getattr(driver, "status", "") or "").upper()
    if status != "ACTIVE":
        d.eligible = False
        d.reasons.append(Reason(
            "DRIVER_NOT_ACTIVE",
            f"the driver's status is {status or 'unset'}; only an ACTIVE "
            f"driver may be assigned"))

    by_type = {}
    for c in credentials:
        by_type[(getattr(c, "credential_type", "") or "").upper()] = c

    for needed in required_credentials(equipment=equipment, hazmat=hazmat):
        cred = by_type.get(needed)

        if cred is None:
            d.eligible = False
            d.reasons.append(Reason(
                "CREDENTIAL_MISSING",
                f"{needed} is required for {equipment}"
                + (" carrying hazmat" if hazmat and needed == "HAZMAT" else "")
                + " and is not on file",
                credential_type=needed))
            continue

        expires = getattr(cred, "expires_on", None)
        if expires is None:
            d.eligible = False
            d.reasons.append(Reason(
                "CREDENTIAL_NO_EXPIRY",
                f"{needed} is on file with no expiry date. An undated "
                f"credential cannot be shown to be valid, and unknown is not "
                f"the same as valid.",
                credential_type=needed))
            continue

        if expires < as_of:
            d.eligible = False
            d.reasons.append(Reason(
                "CREDENTIAL_EXPIRED",
                f"{needed} expired on {expires.isoformat()}",
                credential_type=needed))
            continue

        # The mid-load case. Valid at dispatch, expired at delivery.
        if delivery_by is not None and expires < delivery_by:
            d.eligible = False
            d.reasons.append(Reason(
                "CREDENTIAL_EXPIRES_IN_TRANSIT",
                f"{needed} expires on {expires.isoformat()}, before this load "
                f"delivers on {delivery_by.isoformat()}. The driver would be "
                f"uncredentialed on the road.",
                credential_type=needed))
            continue

        state = (getattr(cred, "verification_state", "") or "").upper()
        if state not in ACCEPTABLE_VERIFICATION:
            d.eligible = False
            d.reasons.append(Reason(
                "CREDENTIAL_NOT_VERIFIED",
                f"{needed} is {state or 'unverified'}. A self-reported "
                f"credential is the driver's word and is not sufficient to "
                f"support an assignment.",
                credential_type=needed))
            continue

        # Advisory: valid now, expiring soon.
        days = (expires - as_of).days
        if days <= 30:
            d.advisories.append(Reason(
                "CREDENTIAL_EXPIRING_SOON",
                f"{needed} expires in {days} day(s), on {expires.isoformat()}",
                credential_type=needed))

    return d


def check_carrier(*, carrier, as_of: Optional[date] = None,
                  max_authority_age_days: int = 30) -> Decision:
    """May this carrier be dispatched?

    The subtle one is authority FRESHNESS. A carrier whose authority was
    checked eight months ago and cached as ACTIVE is not a carrier with active
    authority -- it is a carrier we have not looked at. Revocations are exactly
    what happens in between.
    """
    as_of = as_of or date.today()
    d = Decision(eligible=True)

    if not getattr(carrier, "is_approved", False):
        d.eligible = False
        d.reasons.append(Reason(
            "CARRIER_NOT_APPROVED",
            "this carrier has not been approved for use. Approval is a human "
            "decision and is not implied by being in the table."))

    status = (getattr(carrier, "authority_status", "") or "UNKNOWN").upper()
    if status != "ACTIVE":
        d.eligible = False
        d.reasons.append(Reason(
            "CARRIER_AUTHORITY_NOT_ACTIVE",
            f"operating authority is {status}. UNKNOWN is refused as well as "
            f"REVOKED: not having checked is not the same as having passed."))

    source = (getattr(carrier, "authority_source", "") or "NOT_CONNECTED").upper()
    checked = getattr(carrier, "authority_checked_at", None)
    if source == "NOT_CONNECTED" or checked is None:
        d.eligible = False
        d.reasons.append(Reason(
            "CARRIER_AUTHORITY_UNVERIFIED",
            "no authority check is recorded for this carrier"))
        d.not_connected.append("FMCSA")
    else:
        checked_date = checked.date() if hasattr(checked, "date") else checked
        age = (as_of - checked_date).days
        if age > max_authority_age_days:
            d.eligible = False
            d.reasons.append(Reason(
                "CARRIER_AUTHORITY_STALE",
                f"authority was last checked {age} days ago, beyond the "
                f"{max_authority_age_days}-day limit. A cached ACTIVE is not "
                f"evidence of current authority -- revocation is what happens "
                f"in between."))

    insurance = getattr(carrier, "insurance_expires_on", None)
    if insurance is None:
        d.eligible = False
        d.reasons.append(Reason(
            "CARRIER_INSURANCE_UNKNOWN",
            "no insurance expiry is on file"))
    elif insurance < as_of:
        d.eligible = False
        d.reasons.append(Reason(
            "CARRIER_INSURANCE_EXPIRED",
            f"insurance expired on {insurance.isoformat()}"))
    elif (insurance - as_of).days <= 14:
        d.advisories.append(Reason(
            "CARRIER_INSURANCE_EXPIRING",
            f"insurance expires in {(insurance - as_of).days} day(s)"))

    return d


class AssignmentRefused(RuntimeError):
    """Raised instead of returning, where a caller might ignore a boolean."""

    def __init__(self, decision: Decision):
        self.decision = decision
        codes = ", ".join(decision.refusal_codes) or "unspecified"
        super().__init__(f"assignment refused: {codes}")


def assert_driver_eligible(**kwargs) -> Decision:
    """`check_driver`, but it raises.

    Used on the write path. A function returning False is easy to not check,
    and the failure mode of not checking here is an unlicensed driver on a
    load -- so the write path gets the version that cannot be ignored.
    """
    d = check_driver(**kwargs)
    if not d.eligible:
        raise AssignmentRefused(d)
    return d


def assert_carrier_eligible(**kwargs) -> Decision:
    d = check_carrier(**kwargs)
    if not d.eligible:
        raise AssignmentRefused(d)
    return d
