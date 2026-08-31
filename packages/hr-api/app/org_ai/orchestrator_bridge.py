from .context_builder import build_context
from .decision_engine import decide as decide_action
from .memory import remember


async def decide(db, org_id, event, payload):

    context = await build_context(db, org_id, event, payload)

    decision = await decide_action(context)

    await remember(db, org_id, event, decision)

    return {
        "action": decision.action,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
        "metadata": decision.metadata
    }