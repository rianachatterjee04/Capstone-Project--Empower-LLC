from __future__ import annotations
from typing import Callable, Dict, List, Protocol, Any

class Plugin(Protocol):
    name: str
    def register(self, registry: "PluginRegistry") -> None: ...

class PluginRegistry:
    def __init__(self) -> None:
        self.hooks: Dict[str, List[Callable[..., Any]]] = {}

    def hook(self, hook_name: str, fn: Callable[..., Any]) -> None:
        self.hooks.setdefault(hook_name, []).append(fn)

    def run(self, hook_name: str, *args, **kwargs) -> List[Any]:
        results=[]
        for fn in self.hooks.get(hook_name, []):
            results.append(fn(*args, **kwargs))
        return results
