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
        """
        Simulate salary band lookup.
        """

        # Fake data for now
        return {
            "job_title": job_title,
            "location": location,
            "currency": "USD",
            "min": 90000,
            "mid": 110000,
            "max": 130000,
            "source": "salary.com (stub)",
        }