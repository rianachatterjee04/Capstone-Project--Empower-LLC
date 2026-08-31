from __future__ import annotations
from datetime import timedelta
from temporalio import workflow

@workflow.defn
class EscalationWorkflow:
    @workflow.run
    async def run(self, org_id: str, case_id: str, sla_hours: int):
        await workflow.sleep(timedelta(hours=sla_hours))
        return {"org_id": org_id, "case_id": case_id, "action": "ESCALATE_IF_STILL_OPEN"}
