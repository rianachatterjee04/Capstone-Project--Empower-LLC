from __future__ import annotations

import os

from fastapi import HTTPException
from temporalio.client import Client


async def get_client() -> Client:
    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")

    try:
        return await Client.connect(address)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal is unavailable at {address}. Start Temporal or set TEMPORAL_ADDRESS. Underlying error: {e}",
        )
