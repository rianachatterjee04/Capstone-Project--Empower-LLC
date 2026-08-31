"""
The copilot acknowledges; it does not claim to have acted.

WHY THIS IS A TEST
POST /api/copilot/chat returned, for every message, this fixed sentence:

    "The system analyzed organizational impact and executed policy."

Neither half was established. engine.trigger() returns the moment it schedules
the work -- it does not await it -- so "executed policy" was asserted before
execution began, and stood unchanged when the work then failed. On an HR
surface that sentence is not marketing copy: it says an action was taken
against an employee record.

Two more defects sat with it.

"who should we promote?" was mapped to the event performance.review.finalized
with the question text as employee_name. A question became an assertion that a
review had been finalized. Nothing routes that event today, so nothing was
written -- but it entered the event stream as a finalized review, and any
handler added later would have acted on it.

And the scheduled task was fire-and-forget: no done callback, no strong
reference. If _execute raised, the exception was never retrieved and nothing
was logged; if the loop collected the task, the work vanished. Either way the
caller had already been told "accepted".

Finally, the endpoint answered 500 to any body without a "text" field --
message.get("text") returned None and parse_intent called None.lower().
"""
from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import HTTPException

from app.copilot.event_factory import intent_to_event
from app.copilot.intent_parser import parse_intent
from app.copilot.response_formatter import format_response
from app.workflow.engine import WorkflowEngine

QUEUED = {"accepted": True, "executed": False, "status": "queued"}


def test_the_response_does_not_claim_execution():
    r = format_response("who should we promote?", {"intent": "promotion_advice"}, QUEUED)
    assert r["executed"] is False
    blob = str(r).lower()
    for claim in ("executed policy", "analyzed organizational impact"):
        assert claim not in blob, (
            f"the response still asserts {claim!r}, which nothing has established"
        )


def test_the_response_says_it_is_an_acknowledgement():
    r = format_response("hello", {"intent": "general_question"}, QUEUED)
    assert "acknowledgement" in r["explanation"], (
        "a reader must be able to tell this is a receipt, not an outcome"
    )


def test_a_question_is_not_recorded_as_a_finalized_review():
    """The mapping that turned a question into a completed HR action."""
    for text in ("who should we promote?", "should I promote Dana?"):
        event, payload = intent_to_event(parse_intent(text), text)
        assert event == "copilot.question", f"{text!r} emitted {event!r}"
        assert text not in str(payload.get("employee_name", "")), (
            "the question text is still being carried as an employee name"
        )


def test_no_question_intent_emits_a_past_tense_action_event():
    """The general form. An event name is a claim that something happened, so a
    request for advice must never produce one."""
    offenders = []
    for text in ("who should we promote?", "what is our salary spend?",
                 "how are we paid vs market?", "tell me about the team"):
        event, _ = intent_to_event(parse_intent(text), text)
        if any(event.endswith(suffix) for suffix in (".finalized", ".created", ".approved", ".completed")):
            offenders.append(f"{text!r} -> {event}")
    assert offenders == [], (
        "these questions emit events asserting an action was taken:\n  "
        + "\n  ".join(offenders)
    )


def test_an_action_request_still_reaches_its_workflow():
    """CONTROL, the other direction. Making questions inert must not make the
    copilot inert -- a real instruction still has to route."""
    event, payload = intent_to_event(parse_intent("log a harassment complaint"), "log a harassment complaint")
    assert event == "case.created", event
    assert payload["description"]

    event, payload = intent_to_event(parse_intent("add a candidate for the backend role"), "x")
    assert event == "candidate.created", event


def test_missing_text_is_refused_not_crashed():
    from app.api.deps import required_field
    with pytest.raises(HTTPException) as e:
        required_field({}, "text", what="the message to send")
    assert e.value.status_code == 422


def test_parse_intent_survives_a_none():
    """Defence in depth: this is a plain function and must not raise
    AttributeError from inside a request handler."""
    assert parse_intent(None)["intent"] == "general_question"
    assert parse_intent("")["intent"] == "general_question"


def test_trigger_does_not_report_work_as_executed():
    async def run():
        engine = WorkflowEngine()
        engine._execute = lambda *a, **k: asyncio.sleep(0)   # type: ignore[assignment]
        return engine.trigger("copilot.question", {"query": "x"})

    result = asyncio.run(run())
    assert result["executed"] is False, (
        "trigger() returns before _execute runs, so it must not report the work "
        "as done -- the copilot read this as success and told the user policy "
        "had been executed"
    )
    assert result["status"] == "queued"


def test_a_failing_background_task_is_logged(caplog):
    """MUTATION CONTROL. Before the done-callback, a task that raised had its
    exception retrieved by nobody and logged nowhere. Plant a failure and
    require it to be reported."""
    async def run():
        async def boom():
            raise RuntimeError("driver exploded")
        task = asyncio.ensure_future(boom())
        try:
            await task
        except RuntimeError:
            pass
        return task

    task = asyncio.run(run())
    with caplog.at_level(logging.ERROR, logger="foundry.workflow"):
        WorkflowEngine._log_outcome("case.created", task)

    assert any("EVENT FAILED" in r.message or "EVENT FAILED" in r.getMessage()
               for r in caplog.records), (
        "a background workflow failure produced no log line, so a workflow that "
        "dies leaves the user with an 'accepted' and us with nothing to find"
    )


def test_a_successful_task_is_not_logged_as_a_failure(caplog):
    """CONTROL, the other direction. A callback that shouts on every completion
    trains people to ignore it."""
    async def run():
        async def fine():
            return {"ok": True}
        task = asyncio.ensure_future(fine())
        await task
        return task

    task = asyncio.run(run())
    with caplog.at_level(logging.ERROR, logger="foundry.workflow"):
        WorkflowEngine._log_outcome("case.created", task)
    assert not [r for r in caplog.records if "EVENT FAILED" in r.getMessage()]
