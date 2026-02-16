from __future__ import annotations
import asyncio
from temporalio.worker import Worker
from temporalio import activity
from uuid import UUID

from app.temporal.client import get_client
from app.temporal.workflows.escalation import EscalationWorkflow
from app.temporal.workflows.sync import IntegrationSyncWorkflow
from app.temporal.workflows.replay import IntegrationReplayWorkflow
from app.db.session import async_session_maker
from app.temporal.activities.sync_ats import sync_greenhouse, sync_lever
from app.temporal.activities.replay import replay_events
from app.temporal.activities.screening import enqueue_screening

@activity.defn(name="sync_greenhouse_activity")
async def sync_greenhouse_activity(org_id: str):
    async with async_session_maker() as db:
        res = await sync_greenhouse(db, UUID(org_id))
        await db.commit()
        return res

@activity.defn(name="sync_lever_activity")
async def sync_lever_activity(org_id: str):
    async with async_session_maker() as db:
        res = await sync_lever(db, UUID(org_id))
        await db.commit()
        return res

@activity.defn(name="replay_events_activity")
async def replay_events_activity(org_id: str, provider: str):
    async with async_session_maker() as db:
        res = await replay_events(db, UUID(org_id), provider)
        await db.commit()
        return res

@activity.defn(name="enqueue_screening_activity")
async def enqueue_screening_activity(org_id: str, provider: str):
    async with async_session_maker() as db:
        res = await enqueue_screening(db, UUID(org_id), provider)
        await db.commit()
        return res

async def main():
    client = await get_client()
    worker = Worker(
        client,
        task_queue="foundry-people",
        workflows=[EscalationWorkflow, IntegrationSyncWorkflow, IntegrationReplayWorkflow],
        activities=[sync_greenhouse_activity, sync_lever_activity, replay_events_activity, enqueue_screening_activity],
    )
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
