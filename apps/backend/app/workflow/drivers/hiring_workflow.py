
from .state_machine import StateMachine

pipeline = StateMachine({
    "applied":"screening",
    "screening":"interview",
    "interview":"offer",
    "offer":"accepted",
    "accepted":"onboarding"
})
