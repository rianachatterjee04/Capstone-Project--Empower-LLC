from app.realtime.bus import publish
import uuid

async def request_decision(title: str, message: str, context: dict, actions: list):

    await publish("decision_required", {
        "type": "decision_required",
        "id": f"dec_{uuid.uuid4().hex[:8]}",
        "title": title,
        "message": message,
        "context": context,
        "actions": actions
    })

