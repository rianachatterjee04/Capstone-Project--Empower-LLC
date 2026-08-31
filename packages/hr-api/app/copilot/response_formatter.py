def format_response(text: str, intent: dict, result):
    """Report what actually happened, not what the feature is meant to do.

    This used to return, for every request, whatever the engine said plus the
    fixed sentence:

        "The system analyzed organizational impact and executed policy."

    Neither half was established. engine.trigger() returns {"accepted": True}
    the moment it schedules the work -- before any analysis runs and without
    waiting to see whether it succeeds -- so the claim that policy was EXECUTED
    was made before execution began, and stood even when it then failed.

    On an HR surface that is not marketing copy, it is a statement that an
    action was taken against an employee record. So say what is true: the
    message was understood as this intent, and the work is queued.
    """
    queued = bool(isinstance(result, dict) and result.get("accepted"))
    return {
        "user_message": text,
        "interpreted_intent": intent,
        "system_action": result,
        "queued": queued,
        "executed": False,
        "explanation": (
            "Understood as "
            f"'{intent.get('intent', 'unknown')}' and queued for processing. "
            "No outcome is available yet -- this response is an acknowledgement, "
            "not a result."
            if queued else
            "The message was understood but no action was queued."
        ),
    }
