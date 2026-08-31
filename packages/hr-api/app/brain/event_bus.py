from __future__ import annotations
from typing import Callable, Dict, List

class EventBus:
    """
    Central nervous system.
    Allows workflows to emit events that trigger OTHER workflows.
    """

    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_prefix: str, handler: Callable):
        if event_prefix not in self.subscribers:
            self.subscribers[event_prefix] = []
        self.subscribers[event_prefix].append(handler)

    async def publish(self, event: str, payload: dict):
        results = []

        for prefix, handlers in self.subscribers.items():
            if event.startswith(prefix):
                for h in handlers:
                    try:
                        res = await h(event, payload)
                        results.append(res)
                    except Exception as e:
                        results.append({"handler_error": str(e)})

        return results


bus = EventBus()

