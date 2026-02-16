def parse_intent(text: str) -> dict:
    text = text.lower()

    if "promote" in text:
        return {"intent": "promotion_advice"}

    if "salary" in text or "paid" in text:
        return {"intent": "compensation_analysis"}

    if "hire" in text or "candidate" in text:
        return {"intent": "hiring_action"}

    if "complaint" in text or "harassment" in text:
        return {"intent": "case_analysis"}

    return {"intent": "general_question"}

