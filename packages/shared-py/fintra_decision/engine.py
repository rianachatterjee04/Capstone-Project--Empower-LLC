"""The engine seam. A DecisionEngine is any object that can decide a
DecisionRequest for a domain. The DecisionRegistry routes a request to the first
engine that handles it — "one core, many engines."

The registry is the whole point: adding a domain (HR, procurement, deploy-gating)
is registering an engine, not reshaping the contract. The real Aegis PDP and the
real finance evaluate_payment become two such engines behind adapters; nothing
downstream (ledger, console, receipts) has to know which one answered.
"""
from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from .contract import DecisionRequest, DecisionResponse


@runtime_checkable
class DecisionEngine(Protocol):
    domain: str

    def handles(self, request: DecisionRequest) -> bool:
        """Does this engine own the request? (by domain and/or action type)"""
        ...

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """Return a canonical, sealed DecisionResponse."""
        ...


class NoEngineError(Exception):
    """No registered engine handled the request."""


class DecisionRegistry:
    """Routes DecisionRequests to the first registered engine that handles them.
    Order of registration is priority order."""

    def __init__(self) -> None:
        self._engines: List[DecisionEngine] = []

    def register(self, engine: DecisionEngine) -> DecisionEngine:
        self._engines.append(engine)
        return engine

    def engines(self) -> List[DecisionEngine]:
        return list(self._engines)

    def engine_for(self, request: DecisionRequest) -> Optional[DecisionEngine]:
        for e in self._engines:
            try:
                if e.handles(request):
                    return e
            except Exception:
                # A misbehaving engine must never take the router down; skip it.
                continue
        return None

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        engine = self.engine_for(request)
        if engine is None:
            raise NoEngineError(
                f"no decision engine handles action '{request.action.type}' "
                f"in domain '{request.context.domain}'"
            )
        return engine.decide(request)
