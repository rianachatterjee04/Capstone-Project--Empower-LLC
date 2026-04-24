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
            asyncio.create_task(self._execute(event, payload))
            return {"accepted": True}

        except RuntimeError:
            # Allows usage in scripts/tests where no event loop exists
            return asyncio.run(self._execute(event, payload))

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

