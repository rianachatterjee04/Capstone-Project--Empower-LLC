from __future__ import annotations
import asyncio
import logging
from typing import Dict, Any, Optional
from app.db.session import get_db_session_internal
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.org_ai.orchestrator_bridge import decide
from app.workflow.router import route_action

logger = logging.getLogger("foundry.workflow")


class WorkflowEngine:
    """
    CENTRAL NERVOUS SYSTEM OF FOUNDARY PEOPLE

    Every module calls:
        engine.trigger("event.name", payload)

    Flow:
        API → Engine → OrgAI decision → Router → Drivers → DB/UI
    """

    # ---------------------------------------------------------
    # PUBLIC ENTRYPOINT
    # ---------------------------------------------------------
    def trigger(self, event: str, payload: Optional[Dict[str, Any]] = None):

        payload = payload or {}

        try:
            task = asyncio.create_task(self._execute(event, payload))
            # Without this the task is fire-and-forget: if _execute raises, the
            # exception is never retrieved, nothing is logged, and the caller has
            # already been told {"accepted": True}. Failures were invisible.
            task.add_done_callback(lambda t: self._log_outcome(event, t))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            # "accepted" means scheduled, NOT completed -- _execute has not run
            # yet. Callers were reading this as success and reporting to users
            # that policy had been executed.
            return {"accepted": True, "executed": False, "status": "queued"}

        except RuntimeError:
            # Allows usage in scripts/tests where no event loop exists
            result = asyncio.run(self._execute(event, payload))
            if isinstance(result, dict):
                result.setdefault("executed", True)
            return result

    # Strong references, so the event loop cannot garbage-collect a task that is
    # still running and silently cancel the work we just promised to do.
    _pending: set = set()

    @staticmethod
    def _log_outcome(event: str, task) -> None:
        if task.cancelled():
            logger.error("[EVENT CANCELLED] %s", event)
            return
        exc = task.exception()
        if exc is not None:
            logger.error("[EVENT FAILED] %s: %r", event, exc, exc_info=exc)

    # ---------------------------------------------------------
    # CORE EXECUTION
    # ---------------------------------------------------------
    async def _execute(self, event: str, payload: Dict[str, Any]):

        logger.info(f"[EVENT] {event} | payload={payload}")

        async with get_db_session_internal() as db:

            org_id = payload.get("org_id")

            # 1️⃣ AI decides what company policy wants to happen
            decision = await decide(db, org_id, event, payload)

            logger.info(f"[AI DECISION] {decision}")

            # 2️⃣ Router executes behavior modules
            result = await route_action(db, event, payload, decision)

            logger.info(f"[WORKFLOW RESULT] {result}")

            return result


engine = WorkflowEngine()

