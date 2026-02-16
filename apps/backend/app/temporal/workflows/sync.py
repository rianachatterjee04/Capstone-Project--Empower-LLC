from __future__ import annotations
from temporalio import workflow

@workflow.defn
class IntegrationSyncWorkflow:
    @workflow.run
    async def run(self, org_id: str, provider: str, run_id: str):
        if provider == "greenhouse":
            res = await workflow.execute_activity("sync_greenhouse_activity", org_id, start_to_close_timeout=120)
        elif provider == "lever":
            res = await workflow.execute_activity("sync_lever_activity", org_id, start_to_close_timeout=120)
        else:
            res = {"error": "unsupported_provider"}

        await workflow.execute_activity("enqueue_screening_activity", org_id, provider, start_to_close_timeout=60)
        return {"org_id": org_id, "provider": provider, "run_id": run_id, "result": res}
