from app.realtime.bus import publish
from .memory import remember


async def notify_humans(finding: dict):
    """
    Convert finding into AI conversation.
    """

    message = f"⚠️ Org Guardian: {finding['message']}"

    await publish({
        "type": "guardian_message",
        "payload": finding,
        "text": message
    })

    await remember(finding)

