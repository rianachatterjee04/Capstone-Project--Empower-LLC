import asyncio
from app.db.deps import get_db_session_internal
from .detectors import run_all_detectors
from .notifier import notify_humans

SCAN_INTERVAL = 60  # seconds


async def guardian_loop():
    """
    Runs forever.
    Observes organization state and initiates conversations.
    """

    while True:
        try:
            async with get_db_session_internal() as db:

                findings = await run_all_detectors(db)

                for item in findings:
                    await notify_humans(item)

        except Exception as e:
            print("Guardian error:", e)

        await asyncio.sleep(SCAN_INTERVAL)

