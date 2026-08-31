from .state_machine import StateMachine
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession


pipeline = StateMachine({
    "applied": "screening",
    "screening": "interview",
    "interview": "offer",
    "offer": "accepted",
    "accepted": "onboarding"
})


async def handle_hiring_event(
    db: AsyncSession,
    event: str,
    payload: Dict[str, Any],
    decision: Dict[str, Any],
):
    current_state = payload.get("current_status")

    if not current_state:
        return {"error": "Missing current_status in payload"}

    next_state = pipeline.next(current_state)

    return {
        "previous_state": current_state,
        "next_state": next_state,
    }