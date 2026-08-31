
# Equity Health & Fairness Scoring

class EquityHealth:
    def __init__(self, grants_by_group):
        self.grants_by_group = grants_by_group

    def fairness_index(self):
        # Placeholder logic
        values = list(self.grants_by_group.values())
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return max(0, 100 - variance)  # Lower variance = higher fairness
