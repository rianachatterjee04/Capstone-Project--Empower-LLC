from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List

@dataclass
class SyncResult:
    ok: bool
    details: Dict[str, Any]

class PayrollConnector(ABC):
    @abstractmethod
    async def test_connection(self) -> bool: ...

    @abstractmethod
    async def pull_employees(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def push_compensation_event(self, event: Dict[str, Any]) -> SyncResult: ...
