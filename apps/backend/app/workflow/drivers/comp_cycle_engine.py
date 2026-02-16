
class CompensationCycle:
    def __init__(self,budget):
        self.budget=budget
        self.proposals={}

    def propose(self,eid,amount):
        self.proposals[eid]=amount

    def finalize(self):
        return {"approved":self.proposals,"budget_used":sum(self.proposals.values())}
