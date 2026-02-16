from __future__ import annotations
from temporalio.client import Client
from app.core.config import settings

async def get_client() -> Client:
    return await Client.connect(settings.temporal_address)
