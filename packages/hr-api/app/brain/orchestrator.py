from __future__ import annotations
from app.brain.event_bus import bus
from app.brain.rule_engine import engine as rule_engine

from app.workflow.drivers.hiring_workflow import handle_hiring_event
from app.workflow.drivers.onboarding_enforcement import check_onboarding
from app.workflow.drivers.comp_cycle_engine import handle_comp_event
from app.workflow.drivers.investigation_workflow import handle_case_event


class Brain:

    async def process(self, event: str, payload: dict | None = None):
        payload = payload or {}

        # 1) Built-in workflows
        results = []

        if event.startswith("candidate."):
            results.append(await handle_hiring_event(event, payload))

        if event.startswith("employee.onboarding"):
            results.append(await check_onboarding(payload))

        if event.startswith("comp."):
            results.append(await handle_comp_event(event, payload))

        if event.startswith("case."):
            results.append(await handle_case_event(event, payload))

        # 2) Company rules (custom HR logic)
        rules = await rule_engine.evaluate(event, payload)
        results.extend(rules)

        # 3) Cascade events (autonomous behavior)
        cascade = await bus.publish(event, payload)
        results.extend(cascade)

        return results


brain = Brain()

