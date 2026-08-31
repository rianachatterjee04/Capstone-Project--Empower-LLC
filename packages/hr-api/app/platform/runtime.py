"""The shared platform runtime.

WHAT WAS HERE
`FoundryPlatform` -- a multi-company cap table and option-grant engine
(share classes, strike prices, vesting schedules, dilution) that seeded a
demo cap table with named holders and employee grants at import time. It
is not part of this build, and only one attribute of it was ever used.

Exposing just that attribute keeps the two intelligence routers working
without carrying a cap table behind them.
"""
from .narratives import BoardNarratives


class _Runtime:
    def __init__(self) -> None:
        self.narratives = BoardNarratives()


platform = _Runtime()
