from collections import defaultdict

class OrgGraph:

    def __init__(self, employees: list[dict]):
        self.children = defaultdict(list)
        self.nodes = {}

        for e in employees:
            self.nodes[e["id"]] = e
            if e["manager_id"]:
                self.children[e["manager_id"]].append(e["id"])

    def team_size(self, manager_id: str) -> int:
        """Return total span of control recursively."""
        total = 0
        stack = [manager_id]

        while stack:
            current = stack.pop()
            subs = self.children.get(current, [])
            total += len(subs)
            stack.extend(subs)

        return total

    def pay_distribution(self):
        salaries = [e["salary"] for e in self.nodes.values() if e["salary"]]
        if not salaries:
            return {"avg": 0, "max": 0, "min": 0}

        return {
            "avg": sum(salaries)/len(salaries),
            "max": max(salaries),
            "min": min(salaries)
        }

