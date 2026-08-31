from __future__ import annotations
from typing import Dict, Any
import asyncio
import logging

from app.workflow.drivers.hiring_workflow import handle_hiring_event
from app.workflow.drivers.onboarding_enforcement import check_onboarding
from app.workflow.drivers.comp_cycle_engine import handle_comp_event
from app.workflow.drivers.investigation_workflow import handle_case_event
from app.workflow.rules import evaluate_rules

logger = logging.getLogger("foundry.brain")


class AutonomousBrain:
    """
    Central decision system.

    This replaces router logic entirely.
    Determines:
      • what workflow runs
      • what AI evaluates
      • what cascading events occur
    """

    async def process(self, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:

        logger.info(f"[BRAIN] Processing {event}")

        result = {}

        # -------------------------------------------------
        # HIRING
        # -------------------------------------------------
        if event.startswith("candidate."):
            result = await self._run(handle_hiring_event, event, payload)

        # -------------------------------------------------
        # ONBOARDING
        # -------------------------------------------------
        elif event.startswith("employee.onboarding"):
            result = await self._run(check_onboarding, payload)

        # -------------------------------------------------
        # COMPENSATION
        # -------------------------------------------------
        elif event.startswith("comp."):
            result = await self._run(handle_comp_event, event, payload)

        # -------------------------------------------------
        # INVESTIGATIONS / SAFETY
        # -------------------------------------------------
        elif event.startswith("case."):
            result = await self._run(handle_case_event, event, payload)

        # -------------------------------------------------
        # PERFORMANCE
        # -------------------------------------------------
        elif event.startswith("performance.review.finalized"):
            result = {"analysis": "performance_ai_review_triggered"}

        # -------------------------------------------------
        # RULE ENGINE (always last)
        # -------------------------------------------------
        cascades = await evaluate_rules(event, payload)

        return {
            "event": event,
            "result": result,
            "cascades": cascades
        }

    async def _run(self, fn, *args):
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args)
        return fn(*args)


brain = AutonomousBrain()

