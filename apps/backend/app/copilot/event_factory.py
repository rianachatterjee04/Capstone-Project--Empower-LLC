def intent_to_event(intent: dict, text: str) -> tuple[str, dict]:

    if intent["intent"] == "promotion_advice":
        return "performance.review.finalized", {"employee_name": text}

    if intent["intent"] == "hiring_action":
        return "candidate.created", {"raw_text": text}

    if intent["intent"] == "case_analysis":
        return "case.created", {"description": text}

    return "copilot.question", {"query": text}

