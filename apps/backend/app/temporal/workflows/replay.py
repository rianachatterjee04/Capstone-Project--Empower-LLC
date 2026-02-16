from __future__ import annotations
from temporalio import workflow

@workflow.defn
class IntegrationReplayWorkflow:
    @workflow.run
    async def run(self, org_id: str, provider: str, run_id: str):
        result = await workflow.execute_activity(
            "replay_events_activity",
            org_id, provider,
            start_to_close_timeout=120,
        )
        # After resetting cursors, run a fresh sync
        await workflow.execute_activity("enqueue_screening_activity", org_id, provider, start_to_close_timeout=60)
        return {"org_id": org_id, "provider": provider, "run_id": run_id, "result": result}
