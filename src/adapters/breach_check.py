"""Breach lookups through the official Have I Been Pwned API v3.

The API needs a paid key (https://haveibeenpwned.com/API/Key) and receives the
full email address: it identifies the queried account to HIBP.
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import quote

import httpx

from core.config import AppSettings
from core.domain.models import (
    HaveibeenpwnedBreach,
    HaveibeenpwnedProfiles,
    SocialProfile,
)

_API_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{account}"
_SOURCE = "haveibeenpwned_api_v3"


def _failed_profile(url: str, email: str, *, error: str, status_code: int | None = None) -> SocialProfile:
    return SocialProfile(
        url=url,
        username=email,
        network_name="hibp",
        exists=False,
        metadata={"source": _SOURCE, "status_code": status_code, "error": error},
    )


def _parse_breaches(payload: object) -> list[HaveibeenpwnedBreach]:
    breaches: list[HaveibeenpwnedBreach] = []
    for item in payload if isinstance(payload, list) else []:
        if isinstance(item, dict):
            try:
                breaches.append(HaveibeenpwnedBreach(**item))
            except ValueError:
                continue
    return breaches


def enrich_profiles_with_breach_data(
    emails: Iterable[str],
    *,
    settings: AppSettings | None = None,
) -> list[SocialProfile]:
    settings = settings or AppSettings()
    api_key = settings.hibp_api_key.get_secret_value() if settings.hibp_api_key else ""

    profiles: list[SocialProfile] = []
    with httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        headers={"hibp-api-key": api_key, "user-agent": settings.user_agent},
    ) as client:
        for email in emails:
            url = _API_URL.format(account=quote(email, safe=""))
            if not api_key:
                profiles.append(_failed_profile(url, email, error="hibp_api_key_missing"))
                continue

            try:
                response = client.get(url, params={"truncateResponse": "false"})
            except httpx.HTTPError:
                profiles.append(_failed_profile(url, email, error="hibp_request_failed"))
                continue

            # The API answers 404 when the account appears in no breach.
            if response.status_code == 404:
                breaches: list[HaveibeenpwnedBreach] = []
            elif response.status_code == 200:
                try:
                    breaches = _parse_breaches(response.json())
                except ValueError:
                    profiles.append(_failed_profile(url, email, error="hibp_invalid_response", status_code=200))
                    continue
            else:
                profiles.append(
                    _failed_profile(url, email, error=f"hibp_http_{response.status_code}", status_code=response.status_code)
                )
                continue

            hibp = HaveibeenpwnedProfiles(email=email, breaches=breaches)
            profiles.append(
                SocialProfile(
                    url=url,
                    username=email,
                    network_name="hibp",
                    exists=True,
                    metadata={
                        "source": _SOURCE,
                        "status_code": 200,
                        "breach_count": len(breaches),
                        "breaches": hibp.model_dump(mode="json"),
                    },
                )
            )

    return profiles
