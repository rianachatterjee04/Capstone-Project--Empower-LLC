
from enum import Enum

class OnboardingState(str, Enum):
    OFFERED="offered"
    ACCEPTED="accepted"
    I9_PENDING="i9_pending"
    W4_PENDING="w4_pending"
    ACTIVE="active"

class OnboardingEngine:
    def next(self, state):
        order=[s.value for s in OnboardingState]
        if state not in order: return OnboardingState.OFFERED
        i=order.index(state)
        return order[min(i+1,len(order)-1)]

engine=OnboardingEngine()
