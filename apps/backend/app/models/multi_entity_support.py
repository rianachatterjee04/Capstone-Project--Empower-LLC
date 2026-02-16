
# Multi-Entity / Roll-Up View for Portfolios

class Entity:
    def __init__(self, name, cap_table):
        self.name = name
        self.cap_table = cap_table

class Portfolio:
    def __init__(self):
        self.entities = []

    def add_entity(self, entity):
        self.entities.append(entity)

    def combined_cap_table(self):
        combined = {}
        for e in self.entities:
            for key, value in e.cap_table.items():
                combined[key] = combined.get(key, 0) + value
        return combined
