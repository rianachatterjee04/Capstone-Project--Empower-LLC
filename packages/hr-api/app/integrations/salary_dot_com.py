from __future__ import annotations

from typing import Dict, Any


class SalaryDotComClient:
    """
    Stub Salary.com integration client.
    Replace with real API integration later.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    async def get_salary_band(
        self,
        job_title: str,
        location: str,
    ) -> Dict[str, Any]:
        return {
            "job_title": job_title,
            "location": location,
            "currency": "USD",
            "min": 90000,
            "mid": 110000,
            "max": 130000,
            "source": "salary.com (stub)",
        }

    async def get_salary_range(
        self,
        title: str,
        location: str,
    ) -> Dict[str, Any]:
        band = await self.get_salary_band(title, location)
        return {
            "title": band["job_title"],
            "location": band["location"],
            "currency": band["currency"],
            "min": band["min"],
            "mid": band["mid"],
            "max": band["max"],
            "source": band["source"],
        }
