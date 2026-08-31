"""Workforce projection -- NOT IMPLEMENTED.

These functions used to return constants:

    def forecast_headcount(history):   return {"6_month": 120}
    def attrition_risk(employee):      return 0.12

forecast_headcount was wired to POST /api/intelligence/workforce/forecast and
would have answered 120 for any organisation of any size, from code that never
read the history it was handed. It only escaped notice because the query
feeding it referenced a column that does not exist, so the endpoint 500'd
before reaching the fabrication.

A number with no derivation is worse than no number: it is indistinguishable
from a real one in a screenshot, a board deck, or a customer's plan. If these
are implemented later they must be driven by the organisation's own records.
Until then they refuse, loudly, where a developer will see it -- rather than
returning something a customer might act on.
"""
from __future__ import annotations


class NotImplementedHere(NotImplementedError):
    """Raised instead of returning a fabricated value."""


def forecast_headcount(*_args, **_kwargs):
    raise NotImplementedHere(
        "headcount forecasting is not implemented. "
        "/api/intelligence/workforce/forecast returns measured headcount and "
        "declares the projection unavailable; do not substitute a constant."
    )


def attrition_risk(*_args, **_kwargs):
    raise NotImplementedHere(
        "attrition risk is not implemented. It requires leaver history the "
        "employees table does not record."
    )
