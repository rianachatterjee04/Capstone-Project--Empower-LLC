from __future__ import annotations

from typing import Dict, Any
from urllib.parse import urlencode

from app.core.config import settings


class LinkedInClient:
    """
    Stub LinkedIn integration client.
    Compatible with the router now, easy to replace later with real OAuth/API logic.
    """

    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"

    def __init__(self, access_token: str | None = None):
        self.access_token = access_token

    def build_auth_url(self, org_id: str) -> tuple[str, str]:
        state = f"linkedin-{org_id}"
        redirect_uri = getattr(settings, "lever_redirect_uri", None) or "http://localhost:8000/api/integrations/callback/linkedin"

        query = urlencode(
            {
                "response_type": "code",
                "client_id": "linkedin-client-id-placeholder",
                "redirect_uri": redirect_uri,
                "scope": "r_liteprofile r_emailaddress",
                "state": state,
            }
        )
        return f"{self.AUTH_URL}?{query}", state

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """
        Stub token exchange.
        Replace later with real LinkedIn OAuth token exchange.
        """
        return {
            "access_token": f"linkedin-access-{code}",
            "refresh_token": None,
            "scopes": ["r_liteprofile", "r_emailaddress"],
            "account_id": None,
        }

    async def post_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "success",
            "platform": "linkedin",
            "job_title": payload.get("title"),
        }

    async def fetch_profile(self, linkedin_id: str) -> Dict[str, Any]:
        return {
            "linkedin_id": linkedin_id,
            "name": "Demo Candidate",
            "headline": "Software Engineer",
        }
