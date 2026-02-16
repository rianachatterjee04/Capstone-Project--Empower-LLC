from __future__ import annotations
from typing import Any, Dict, List
from app.integrations.base import PayrollConnector, SyncResult

class GustoConnector(PayrollConnector):
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    async def test_connection(self) -> bool:
        # TODO: OAuth2 + API call
        return False

    async def pull_employees(self) -> List[Dict[str, Any]]:
        # TODO: map to employees table
        return []

    async def push_compensation_event(self, event: Dict[str, Any]) -> SyncResult:
        # TODO: create/update in provider
        return SyncResult(ok=False, details={"reason":"not_implemented"})
