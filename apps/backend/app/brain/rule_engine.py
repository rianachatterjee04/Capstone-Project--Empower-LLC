from __future__ import annotations
from typing import List, Dict, Any

class Rule:
    def __init__(self, name: str, condition, action):
        self.name = name
        self.condition = condition
        self.action = action


class RuleEngine:
    """
    Evaluates company rules dynamically.
    HR can configure behavior without changing code.
    """

    def __init__(self):
        self.rules: List[Rule] = []

    def register(self, rule: Rule):
        self.rules.append(rule)

    async def evaluate(self, event: str, payload: Dict[str, Any]):
        results = []

        for rule in self.rules:
            try:
                if rule.condition(event, payload):
                    res = await rule.action(event, payload)
                    results.append({"rule": rule.name, "result": res})
            except Exception as e:
                results.append({"rule": rule.name, "error": str(e)})

        return results


engine = RuleEngine()

