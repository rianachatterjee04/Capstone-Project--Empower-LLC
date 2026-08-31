def parse_intent(text: str | None) -> dict:
    # Defence in depth: the router refuses a missing message, but this is a
    # plain function and a None reaching it must not raise AttributeError
    # from inside a request handler.
    text = (text or "").lower()

    if "promote" in text:
        return {"intent": "promotion_advice"}

    if "salary" in text or "paid" in text:
        return {"intent": "compensation_analysis"}

    if "hire" in text or "candidate" in text:
        return {"intent": "hiring_action"}

    if "complaint" in text or "harassment" in text:
        return {"intent": "case_analysis"}

    return {"intent": "general_question"}

