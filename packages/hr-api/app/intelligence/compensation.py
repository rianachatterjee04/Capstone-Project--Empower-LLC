"""Compensation analysis -- NOT IMPLEMENTED HERE.

The real implementations live in app/api/routers/intelligence/compensation.py
(pay-compression detection over same title/level groups, and raise simulation).
This module held six lines of stubs:

    def detect_pay_compression(employees):    return []
    def simulate_raise(employee_id, percent): return {"risk": "low"}

and it was the one the intelligence router actually imported. So the wired code
path answered "no pay compression found" for every organisation without looking
at a single salary, while the detector that does the work sat beside it,
unimported. On a deployment whose employees table carries salary, that is a
false all-clear on a pay-equity question.

Import the router-package module instead. These raise so the mistake cannot be
made silently a second time.
"""
from __future__ import annotations

_REAL = "app.api.routers.intelligence.compensation"


def detect_pay_compression(*_args, **_kwargs):
    raise NotImplementedError(
        f"stub -- import {_REAL} instead. Returning [] here reads as "
        "'no pay compression detected' without having examined any salary."
    )


def simulate_raise(*_args, **_kwargs):
    raise NotImplementedError(f"stub -- import {_REAL} instead.")
