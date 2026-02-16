from app.workflow.engine import engine
from .intent_parser import parse_intent
from .event_factory import intent_to_event
from .response_formatter import format_response


async def run_copilot(org_id: str, user_id: str, role: str, text: str):

    intent = parse_intent(text)
    event, payload = intent_to_event(intent, text)

    payload["org_id"] = org_id
    payload["actor_id"] = user_id
    payload["actor_role"] = role

    result = engine.trigger(event, payload)

    return format_response(text, intent, result)

