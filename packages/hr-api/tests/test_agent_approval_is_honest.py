"""
Approving an agent action reports what it did, and does not report an approval
it failed to record.

WHY THIS IS A TEST
Approving "Run AI screening on 4 unscored candidates" returned 200 and
{"approved": true}. Four candidates stayed unscored, the button went on saying
"Approve", and the natural next move is to press it again. The endpoint records
the human decision to an audit event; it never executes the action, and nothing
in the response or the screen said so.

Worse, the audit write was wrapped in a bare `except: rollback` and the
endpoint still returned {"approved": true}. An approval is the human-in-the-loop
gate. Claiming to have recorded one that was rolled back is the last thing this
endpoint should do — the audit log is the only evidence the decision happened.
"""
from __future__ import annotations

import inspect
import re

from app.api.routers import agents as A


def _source():
    return inspect.getsource(A.approve_action)


def test_the_response_says_the_action_was_not_executed():
    src = _source()
    assert '"executed": False' in src, (
        "the approval response no longer states that it does not run the action")
    assert "next_step" in src, "the response no longer says what still has to happen"


def test_a_failed_audit_write_is_not_reported_as_an_approval():
    src = _source()
    # The except must raise, not fall through to a success return.
    except_block = src.split("except Exception")[-1]
    assert "raise HTTPException" in except_block, (
        "the audit write can still fail while the endpoint returns success — "
        "an approval that was rolled back must not be reported as granted")
    assert '"approved": False' in except_block, (
        "the failure response does not say the approval was refused")
    # ...and it must not be a silent pass.
    assert not re.search(r"except Exception[^\n]*:\s*\n\s*await db\.rollback\(\)\s*\n\s*return",
                         src), "the swallow-and-return-success shape is back"


def test_the_success_path_still_records_to_the_audit_log():
    """CONTROL. Refusing on failure is only right if success still writes."""
    src = _source()
    assert "AuditEvent(" in src
    assert "action_approved" in src
    assert '"recorded": True' in src
