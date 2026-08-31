"""Live carrier authority from FMCSA's public Socrata dataset.

WHAT THIS IS FOR
`eligibility.check_carrier` refuses a carrier whose authority was last checked
more than 30 days ago, because a cached ACTIVE is not evidence of current
authority -- revocation is exactly what happens in between. That refusal is
only useful if something can actually go and check.

WHAT IT ESTABLISHES, AND WHAT IT DOES NOT
The Company Census File records a carrier's operating status as FMCSA holds
it. That is a real, citable fact about a registration.

It is NOT a safety rating, NOT an insurance certificate, and NOT a
representation that this carrier is fit for your freight. A broker still has
to check insurance separately, which is why `check_carrier` has its own
insurance test that this does not satisfy.

PROVENANCE TRAVELS WITH THE VALUE
Every result carries the dataset, the row's own vintage, and when we retrieved
it. A carrier record's `authority_source` becomes FMCSA_LIVE only on a fresh
successful fetch; anything else stays FMCSA_CACHED or NOT_CONNECTED, and the
30-day staleness rule then does its job.

RIGHTS
This is a public register consulted about a SPECIFIC carrier we are about to
do business with. That is what it is for. It does not license outreach, and
`demo_commercial_loop.py` refuses to market to FMCSA-sourced names for exactly
that reason.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

FMCSA_VERSION = "fmcsa-authority-2026.08.29"

DOMAIN = "https://data.transportation.gov"
STATUS_DATASET = "az4n-8mr2"          # Company Census File
STATUS_URL = f"{DOMAIN}/resource/{STATUS_DATASET}.json"

CONNECT_TIMEOUT = 10

#: How FMCSA spells it -> how the trucking domain does.
_STATUS_MAP = {
    "A": "ACTIVE", "ACTIVE": "ACTIVE",
    "I": "INACTIVE", "INACTIVE": "INACTIVE",
    "R": "REVOKED", "REVOKED": "REVOKED",
    "N": "INACTIVE",
}


@dataclass
class AuthorityLookup:
    dot_number: str
    found: bool
    authority_status: str = "UNKNOWN"
    legal_name: Optional[str] = None
    dba_name: Optional[str] = None
    state: Optional[str] = None
    #: Everything needed to defend the value later.
    source: str = "NOT_CONNECTED"
    dataset: str = STATUS_DATASET
    retrieved_at: Optional[str] = None
    record_vintage: Optional[str] = None
    raw_status: Optional[str] = None
    error: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @property
    def is_live(self) -> bool:
        return self.source == "FMCSA_LIVE"

    def as_dict(self) -> dict:
        return {
            "dot_number": self.dot_number, "found": self.found,
            "authority_status": self.authority_status,
            "legal_name": self.legal_name, "dba_name": self.dba_name,
            "state": self.state, "source": self.source,
            "dataset": self.dataset, "retrieved_at": self.retrieved_at,
            "record_vintage": self.record_vintage,
            "raw_status": self.raw_status, "error": self.error,
            "notes": self.notes,
        }


def app_token() -> Optional[str]:
    """Optional Socrata token. Raises the rate limit; not required."""
    return (os.environ.get("SOCRATA_APP_TOKEN")
            or os.environ.get("FMCSA_APP_TOKEN") or None)


def connectivity() -> dict:
    """What this deployment can do, without pretending."""
    return {
        "source": "FMCSA Company Census File (Socrata)",
        "dataset": STATUS_DATASET,
        "endpoint": STATUS_URL,
        "app_token_configured": bool(app_token()),
        "token_required": False,
        "note": ("No credential is required. A Socrata app token only raises "
                 "the anonymous rate limit. Establishes OPERATING STATUS "
                 "only — not a safety rating and not insurance."),
    }


def _fetch(dot_number: str, *, opener=None) -> Any:
    params = {"$where": f"dot_number='{dot_number}'", "$limit": "1"}
    url = f"{STATUS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "FintraTrucking/1.0 (carrier qualification)",
        **({"X-App-Token": app_token()} if app_token() else {}),
    })
    _open = opener or urllib.request.urlopen
    with _open(req, timeout=CONNECT_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def lookup(dot_number: str, *, opener=None) -> AuthorityLookup:
    """Check one carrier's operating status, right now.

    Every failure produces UNKNOWN with source NOT_CONNECTED and the reason.
    It never guesses ACTIVE: `check_carrier` refuses UNKNOWN as firmly as it
    refuses REVOKED, because not having checked is not the same as having
    passed, and a lookup that failed open would quietly defeat that.
    """
    dot = str(dot_number or "").strip()
    now = datetime.now(timezone.utc).isoformat()

    if not dot.isdigit():
        return AuthorityLookup(
            dot_number=dot, found=False, error="DOT number must be numeric",
            notes=["nothing was requested; the identifier was not usable"])

    try:
        rows = _fetch(dot, opener=opener)
    except Exception as exc:                       # noqa: BLE001
        return AuthorityLookup(
            dot_number=dot, found=False, source="NOT_CONNECTED",
            retrieved_at=now, error=f"{type(exc).__name__}: {exc}",
            notes=["the lookup failed, so the status is UNKNOWN. It is not "
                   "assumed to be ACTIVE."])

    if not rows:
        return AuthorityLookup(
            dot_number=dot, found=False, source="FMCSA_LIVE",
            retrieved_at=now,
            notes=[f"no row for DOT {dot} in the census file. An unregistered "
                   f"or mistyped number, not a carrier in good standing."])

    row = rows[0] if isinstance(rows, list) else rows
    raw = str(row.get("status_code") or row.get("carrier_operation")
              or row.get("status") or "").strip().upper()
    mapped = _STATUS_MAP.get(raw, "UNKNOWN")

    notes = []
    if mapped == "UNKNOWN" and raw:
        notes.append(f"FMCSA returned status {raw!r}, which this does not map. "
                     f"Treated as UNKNOWN rather than guessed.")
    notes.append("Operating status only. Not a safety rating, and not "
                 "evidence of insurance.")

    return AuthorityLookup(
        dot_number=dot, found=True, authority_status=mapped,
        legal_name=row.get("legal_name") or row.get("name"),
        dba_name=row.get("dba_name"),
        state=row.get("phy_state") or row.get("state"),
        source="FMCSA_LIVE", retrieved_at=now,
        record_vintage=(row.get("mcs150_date") or row.get("add_date")
                        or row.get(":updated_at")),
        raw_status=raw or None, notes=notes)


async def refresh_carrier(db, *, org_id, carrier_id, opener=None) -> dict:
    """Look a carrier up and write the result onto its row.

    The write is the point: `check_carrier` reads authority_checked_at, and a
    carrier that has never been refreshed is refused. This is what lets a
    dispatcher fix that rather than override it.
    """
    from sqlalchemy import text

    row = (await db.execute(text("""
        SELECT dot_number, name FROM public.trucking_carriers
        WHERE org_id = :o AND id = :c"""),
        {"o": org_id, "c": carrier_id})).first()
    if row is None:
        raise ValueError("no such carrier for this organisation")
    if not row[0]:
        return {"updated": False,
                "reason": ("this carrier has no DOT number on file, so there "
                           "is nothing to look up. Add one first."),
                "carrier": row[1]}

    result = lookup(row[0], opener=opener)

    if result.source == "FMCSA_LIVE":
        await db.execute(text("""
            UPDATE public.trucking_carriers
            SET authority_status = :s, authority_source = 'FMCSA_LIVE',
                authority_checked_at = now()
            WHERE org_id = :o AND id = :c"""),
            {"s": result.authority_status, "o": org_id, "c": carrier_id})
    # A failed lookup deliberately does NOT touch authority_checked_at. If it
    # did, a string of failures would keep the carrier looking freshly
    # verified while nothing had actually been checked.

    return {"updated": result.source == "FMCSA_LIVE",
            "carrier": row[1], **result.as_dict()}
