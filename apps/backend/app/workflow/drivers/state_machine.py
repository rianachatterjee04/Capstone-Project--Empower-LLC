
class StateMachine:
    def __init__(self, transitions):
        self.transitions = transitions

    def next(self, state):
        return self.transitions.get(state, state)
