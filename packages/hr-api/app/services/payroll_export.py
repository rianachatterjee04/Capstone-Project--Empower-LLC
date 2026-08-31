"""Handing finalised comp decisions to payroll — NOT CONNECTED.

WHAT THIS USED TO SAY
    def export_payroll(data):
        return {"exported_records": len(data)}

It counted the rows it was given and reported them as "exported_records".
Nothing was sent anywhere. POST /api/compcycle/{id}/finalize answered

    {"status": "closed", "payroll_export": {"exported_records": 1}}

which reads, to the finance lead closing a merit cycle, as confirmation that
the approved raises reached payroll. They did not, and the cycle was closed.

A count of what WOULD have been sent is a useful thing to return. Calling it
"exported" is a claim about money having moved.
"""
from __future__ import annotations


def export_payroll(data) -> dict:
    """Report what is ready for payroll, and that nothing has been sent.

    `data` is the list of approved comp decisions the cycle wants to hand over.
    """
    rows = list(data or [])
    return {
        "records_ready": len(rows),
        "exported": False,
        "available": False,
        "reason": (
            "no payroll export connector is configured, so these decisions have "
            "not been sent to payroll. They are recorded in comp_proposals and "
            "can be exported once a connector is connected."
        ),
    }
