from fastapi import APIRouter
from app.workflow.engine import engine

router = APIRouter(prefix="/decisions", tags=["decisions"])

@router.post("/respond")
async def respond(decision_id: str, action: str, context: dict):

    # Convert UI decision into workflow event
    engine.trigger(
        "decision.made",
        {
            "decision_id": decision_id,
            "action": action,
            **context
        }
    )

    return {"accepted": True}

