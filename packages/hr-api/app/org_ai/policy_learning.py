policy_memory = {}

def record_outcome(event: str, action: str, outcome: str):
    key = f"{event}:{action}"
    stats = policy_memory.setdefault(key, {"success":0,"fail":0})

    if outcome == "success":
        stats["success"] += 1
    else:
        stats["fail"] += 1


def confidence(event: str, action: str) -> float:
    stats = policy_memory.get(f"{event}:{action}")
    if not stats:
        return 0.5
    total = stats["success"] + stats["fail"]
    return stats["success"]/total if total else 0.5

