"""
The thin-margin tile and the margin table mean the same thing by "revenue".

WHY THIS IS A TEST
The trucking board showed, on one screen:

    Loads at or under 15% margin ......... 2      (tile + drill)
    ...
    L-31108   $5,256.25   $4,418.50   $837.75   15.94%
    1 load below the 15% floor.                  (margin table)

Two counts of one question, disagreeing, four inches apart.

app/trucking/billing.py computes contribution margin as
`linehaul + accessorials` from the invoice. The thin-margin drill used
`l.customer_rate_cents` — the agreed linehaul rate, with no accessorials. On
L-31108 that is 512500 against 525625: 13.79% instead of 15.94%, which puts it
under a 15% floor it is actually above.

Understating revenue overstates thinness. On this screen that means sending a
broker to renegotiate a load that was never thin, and it is the exact failure
the authority ladder is meant to prevent — two derivations of one number, with
nothing reconciling them.
"""
from __future__ import annotations

import re

from app.trucking import drilldown as D


def _thin():
    # DRILLS is keyed by drill key, not a list.
    return D.DRILLS["thin_margin"]


def test_the_drill_reads_invoice_revenue():
    sql = _thin().source + " " + _thin().where
    assert "trucking_invoices" in sql, (
        "the thin-margin drill no longer looks at the invoice, so it is back to "
        "measuring margin on the linehaul rate alone")
    assert "accessorial_cents" in sql, (
        "invoice revenue is being read without accessorials, which is the "
        "difference that made L-31108 look thin")


def test_it_falls_back_to_the_agreed_rate_when_not_invoiced():
    """An uninvoiced load has no accessorials recorded; the rate is all there is."""
    sql = _thin().where + " " + _thin().columns
    assert "customer_rate_cents" in sql
    assert "COALESCE" in sql.upper()


def test_the_floor_is_still_defined_once():
    """CONTROL. Both the tile label and the predicate read the same constant."""
    thin = _thin()
    assert f"{D.THIN_MARGIN_PCT:g}" in thin.label
    assert str(D.THIN_MARGIN_PCT) in thin.where
    assert D.THIN_MARGIN_PCT == D.MARGIN_FLOOR_PCT


def test_billing_still_defines_revenue_as_linehaul_plus_accessorials():
    """CONTROL. This drill was aligned TO billing; if billing moves, they part.

    The whole fix is that two computations agree. Pinning only the drill would
    let the other side drift and reintroduce the discrepancy from the far end.
    """
    import inspect
    from app.trucking import billing as B
    src = inspect.getsource(B)
    assert re.search(r"revenue\s*=\s*linehaul\s*\+\s*acc_rev", src), (
        "billing.py no longer computes revenue as linehaul + accessorials, so "
        "the thin-margin drill is now aligned to something that changed")
