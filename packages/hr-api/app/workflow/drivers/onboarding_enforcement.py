from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession


async def check_onboarding(
    db: AsyncSession,
    event: str,
    payload: Dict[str, Any],
    decision: Dict[str, Any],
):
    """
    Onboarding enforcement driver.
    Stub implementation for now.
    """

    return {
        "message": "Onboarding enforcement checked",
        "event": event,
    }

def required_documents():
    return ["I9_section1","I9_section2","W4","DirectDeposit"]

def is_complete(submitted):
    return all(doc in submitted for doc in required_documents())
