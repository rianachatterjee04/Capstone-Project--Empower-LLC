from typing import Dict, Any


class LinkedInClient:
    """
    Stub LinkedIn integration client.
    Replace with real OAuth + API integration later.
    """

    def __init__(self, access_token: str | None = None):
        self.access_token = access_token

    async def post_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate posting a job to LinkedIn.
        """
        return {
            "status": "success",
            "platform": "linkedin",
            "job_title": payload.get("title"),
        }

    async def fetch_profile(self, linkedin_id: str) -> Dict[str, Any]:
        """
        Simulate fetching a LinkedIn profile.
        """
        return {
            "linkedin_id": linkedin_id,
            "name": "Demo Candidate",
            "headline": "Software Engineer",
        }