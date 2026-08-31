"""Stub for the HR education assistant - replace with a real implementation.

Renamed from `EquityBot`: this build has no cap table, and a class named for
equity invited exactly the answers the removed `app/models` copy of this file
gave -- confident explanations of vesting and what happens to unvested shares,
on a system holding no equity data at all.
"""
from __future__ import annotations


class EducationBot:
    def answer(self, question: str) -> str:
        return "Education chatbot not yet implemented."


# Back-compat alias for any caller still importing the old name.
EquityBot = EducationBot
