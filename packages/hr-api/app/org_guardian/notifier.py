from app.realtime.bus import publish
from .memory import remember


async def notify_humans(finding: dict):
    """
    Convert finding into AI conversation.
    """

    message = f"⚠️ Org Guardian: {finding['message']}"

    # publish(event, payload) — this previously passed a single dict, which raised
    # TypeError against the 2-arg signature, so guardian messages never reached the
    # wire. The bus drops events it cannot attribute to an org, so if `finding`
    # carries no org_id this is logged and discarded rather than cross-published.
    await publish("guardian_message", {
        "type": "guardian_message",
        "payload": finding,
        "text": message
    })

    await remember(finding)

