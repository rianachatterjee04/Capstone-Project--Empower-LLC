def intent_to_event(intent: dict, text: str) -> tuple[str, dict]:
    """Map a parsed chat intent to a workflow event.

    "who should we promote?" used to become:

        ("performance.review.finalized", {"employee_name": "who should we promote?"})

    A question was turned into an event asserting that a performance review had
    been FINALIZED, carrying the question itself as the employee's name. Nothing
    routes that event today, so nothing was written -- but it was logged into
    the event stream as a finalized review, and any handler added later would
    have acted on it. An event name is a claim about something that happened.

    Asking for advice is a question. It emits a question.
    """
    kind = intent.get("intent")

    if kind == "hiring_action":
        return "candidate.created", {"raw_text": text}

    if kind == "case_analysis":
        return "case.created", {"description": text}

    # promotion_advice, compensation_analysis and general_question are all
    # requests for an answer, not records of an action.
    return "copilot.question", {"query": text, "asked_intent": kind}
