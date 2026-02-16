def format_response(text: str, intent: dict, result):

    return {
        "user_message": text,
        "interpreted_intent": intent,
        "system_action": result,
        "explanation": "The system analyzed organizational impact and executed policy."
    }

