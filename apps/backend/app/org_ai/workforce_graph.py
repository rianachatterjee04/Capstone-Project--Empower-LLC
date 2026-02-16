def compute_relationship_risk(context):
    """
    Detect toxic manager patterns
    """

    if not context.history:
        return 0.0

    complaints = sum(1 for h in context.history if h["event_type"].startswith("case."))
    reviews = sum(1 for h in context.history if h["event_type"] == "review.finalized")

    if reviews == 0:
        return 0.0

    return min(1.0, complaints / reviews)

