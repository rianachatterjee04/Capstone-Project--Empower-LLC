"""
An audit payload can always be written.

WHY THIS IS A TEST
Approving a request wrote

    payload={"amount": row["amount"], "type": row["type"]}

where amount comes from a numeric column and is therefore a Decimal. JSONB
serialisation raised

    TypeError: Object of type Decimal is not JSON serializable

which killed the whole transaction: the approval was not recorded, and neither
was its audit event. Approving anything was impossible.

It went unnoticed because approving ALSO requires a matching approval_authority
row, and none is configured on a fresh deployment — so every attempt was
refused at 403 long before it reached the serialiser. One control was hiding a
defect behind another. The moment authority is configured correctly, the
feature crashes.

Sanitising at the column, rather than at the three call sites that happened to
pass money, means the next caller who puts a Decimal, a UUID or a date into an
audit payload does not rediscover this. An audit write is the last place to
want a serialisation surprise.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.json_utils import json_safe
from app.db.models import AuditEvent

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _event(payload: dict) -> AuditEvent:
    return AuditEvent(
        org_id=ORG,
        actor_user_id=ORG,
        actor_role="owner",
        event_type="approval.approved",
        entity_type="approval_request",
        entity_id=ORG,
        payload=payload,
    )


def test_a_decimal_amount_survives_assignment():
    """The exact payload that killed the approval transaction."""
    ev = _event({"amount": Decimal("25000.00"), "type": None})
    json.dumps(ev.payload)  # must not raise
    assert ev.payload["amount"] == 25000.0


def test_the_other_types_that_reach_audit_payloads():
    ev = _event({
        "id": uuid.uuid4(),
        "when": datetime(2026, 8, 30, 12, 0, 0),
        "on": date(2026, 8, 30),
        "amount": Decimal("1.25"),
    })
    json.dumps(ev.payload)
    assert isinstance(ev.payload["id"], str)
    assert ev.payload["on"] == "2026-08-30"
    assert ev.payload["amount"] == 1.25


def test_nested_structures_are_sanitised():
    """Money usually arrives inside something."""
    ev = _event({"rows": [{"amount": Decimal("3")}, {"amount": Decimal("4")}],
                 "totals": {"sum": Decimal("7")}})
    json.dumps(ev.payload)
    assert ev.payload["rows"][1]["amount"] == 4.0
    assert ev.payload["totals"]["sum"] == 7.0


def test_ordinary_payloads_are_unchanged():
    """CONTROL. A coercion that rewrites healthy payloads would be its own bug."""
    original = {"type": "comp_change", "n": 3, "ok": True, "note": None, "tags": ["a"]}
    ev = _event(dict(original))
    assert ev.payload == original


def test_the_raw_payload_really_was_unserialisable():
    """MUTATION CONTROL. If Decimal became JSON-serialisable, this guard would
    pass for a reason that has nothing to do with the fix."""
    try:
        json.dumps({"amount": Decimal("25000.00")})
    except TypeError:
        return
    raise AssertionError(
        "json.dumps now accepts Decimal, so this test no longer demonstrates the "
        "defect it was written for"
    )


def test_json_safe_is_what_the_column_uses():
    """The column delegates rather than reimplementing, so the two cannot drift."""
    value = {"amount": Decimal("2.50"), "id": uuid.uuid4()}
    ev = _event(dict(value))
    assert ev.payload == json_safe(value)
