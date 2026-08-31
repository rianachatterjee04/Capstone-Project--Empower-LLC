from fastapi import APIRouter, Depends
from app.api.deps import require_org, Actor, required_field
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
        # A chat turn with no text is a bad request, not a server fault.
        # message.get("text") returned None and parse_intent called
        # None.lower(), so POST /api/copilot/chat answered 500 to any body
        # that omitted the field.
        text=required_field(message, "text", what="the message to send"),
    )
    return response

