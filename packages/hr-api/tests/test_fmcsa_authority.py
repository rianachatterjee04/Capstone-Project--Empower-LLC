"""Live carrier authority, and the ways it must fail.

`check_carrier` refuses a carrier whose authority was last checked more than
30 days ago, because a cached ACTIVE is not evidence of current authority.
That refusal is only useful if something can actually check -- and it is only
SAFE if a failed check never looks like a successful one.

So the tests here are mostly about failure. The network test is marked and
skipped by default; everything else runs against a stubbed opener, because a
control that only works when the internet does is not a control.
"""
from __future__ import annotations

import io
import json
import os

import pytest

from app.trucking import fmcsa_authority as F


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(payload, *, boom=None):
    def open_(req, timeout=None):
        if boom is not None:
            raise boom
        return _Resp(json.dumps(payload).encode())
    return open_


ROW = {
    "dot_number": "2194844",
    "legal_name": "HANSEL KING",
    "dba_name": None,
    "phy_state": "TX",
    "status_code": "A",
    "mcs150_date": "2024-03-11T00:00:00.000",
}


# ===========================================================================
# The happy path carries its provenance
# ===========================================================================

def test_a_found_carrier_returns_status_with_its_source_and_vintage():
    r = F.lookup("2194844", opener=_opener([ROW]))
    assert r.found is True
    assert r.authority_status == "ACTIVE"
    assert r.source == "FMCSA_LIVE"
    assert r.legal_name == "HANSEL KING"
    assert r.retrieved_at, "a value with no retrieval time cannot be aged"
    assert r.record_vintage == ROW["mcs150_date"]
    assert r.dataset == F.STATUS_DATASET


def test_the_result_says_what_it_does_not_establish():
    """A broker reading ACTIVE must not conclude 'safe to use'."""
    r = F.lookup("2194844", opener=_opener([ROW]))
    joined = " ".join(r.notes).lower()
    assert "not a safety rating" in joined
    assert "insurance" in joined


@pytest.mark.parametrize("raw,expected", [
    ("A", "ACTIVE"), ("ACTIVE", "ACTIVE"),
    ("I", "INACTIVE"), ("INACTIVE", "INACTIVE"),
    ("R", "REVOKED"), ("REVOKED", "REVOKED"),
])
def test_status_codes_map(raw, expected):
    r = F.lookup("1", opener=_opener([{**ROW, "status_code": raw}]))
    assert r.authority_status == expected


def test_an_unmapped_status_becomes_unknown_rather_than_a_guess():
    r = F.lookup("1", opener=_opener([{**ROW, "status_code": "ZZ"}]))
    assert r.authority_status == "UNKNOWN"
    assert any("does not map" in n for n in r.notes)


# ===========================================================================
# Failure must never look like success
# ===========================================================================

def test_a_network_failure_yields_unknown_and_not_connected():
    """The load-bearing one.

    If a failed lookup returned ACTIVE, or even quietly returned the previous
    value, the 30-day staleness refusal would be defeated by an outage.
    """
    r = F.lookup("2194844", opener=_opener(None, boom=OSError("timeout")))
    assert r.found is False
    assert r.authority_status == "UNKNOWN"
    assert r.source == "NOT_CONNECTED"
    assert "not assumed to be ACTIVE" in " ".join(r.notes)


def test_an_unregistered_dot_is_not_a_carrier_in_good_standing():
    r = F.lookup("99999999999", opener=_opener([]))
    assert r.found is False
    assert r.authority_status == "UNKNOWN"
    # The fetch DID succeed, so the source is live; the carrier simply is not
    # there. Those are different facts and are recorded differently.
    assert r.source == "FMCSA_LIVE"


def test_a_non_numeric_identifier_is_refused_before_any_request():
    called = {"n": 0}

    def opener(req, timeout=None):
        called["n"] += 1
        raise AssertionError("should not have been called")

    r = F.lookup("MC-12345", opener=opener)
    assert r.found is False
    assert called["n"] == 0


def test_unknown_is_refused_by_the_eligibility_gate():
    """The join between this module and the control it feeds."""
    from datetime import date, datetime, timedelta, timezone
    from app.trucking import eligibility as E

    carrier = type("C", (), {
        "is_approved": True, "authority_status": "UNKNOWN",
        "authority_source": "FMCSA_LIVE",
        "authority_checked_at": datetime.now(timezone.utc),
        "insurance_expires_on": date.today() + timedelta(days=90)})()
    d = E.check_carrier(carrier=carrier, as_of=date.today())
    assert d.eligible is False
    assert "CARRIER_AUTHORITY_NOT_ACTIVE" in d.refusal_codes


# ===========================================================================
# Connectivity is described honestly
# ===========================================================================

def test_connectivity_states_the_credential_boundary():
    c = F.connectivity()
    assert c["token_required"] is False
    assert "OPERATING STATUS only" in c["note"]
    assert F.STATUS_DATASET in c["endpoint"]


@pytest.mark.skipif(
    os.environ.get("FINTRA_ALLOW_LIVE_FMCSA") != "1",
    reason=("makes a real request to data.transportation.gov. Set "
            "FINTRA_ALLOW_LIVE_FMCSA=1 to run it. A test that needs the "
            "internet must not be part of the default gate."))
def test_a_real_lookup_against_the_live_dataset():
    r = F.lookup("2194844")
    assert r.source == "FMCSA_LIVE"
    assert r.retrieved_at
    if r.found:
        assert r.authority_status in ("ACTIVE", "INACTIVE", "REVOKED", "UNKNOWN")
