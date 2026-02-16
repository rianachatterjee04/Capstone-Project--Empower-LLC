from fastapi import APIRouter, Depends
from app.api.deps import require_org, Actor
from .copilot_orchestrator import run_copilot

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/chat")
async def chat(message: dict, actor: Actor = Depends(require_org)):
    """
    Main conversational interface to the HR OS
    """
    response = await run_copilot(
        org_id=actor.org_id,
        user_id=actor.user_id,
        role=actor.role,
        text=message.get("text")
    )
    return response

