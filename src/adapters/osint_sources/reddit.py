"""Scanner OSINT: Reddit.

Fase 2:
- Usa el endpoint JSON `about.json` para extraer metadata ligera.
"""

from __future__ import annotations

from typing import Any

from adapters.specific_scrapers import fetch_reddit_deep
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class RedditScanner(OSINTScanner):
    _base_url = "https://www.reddit.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        public_url = f"{self._base_url}/user/{username}/"

        api = await fetch_reddit_deep(username=username, settings=self._settings)
        exists = api is not None

        metadata: dict[str, Any] = {
            "source": "reddit_about_json",
        }
        if api:
            metadata.update(api)

        bio = None
        image_url = None
        if api:
            if isinstance(api.get("public_description"), str):
                bio = api.get("public_description")
            if isinstance(api.get("icon_img"), str) and api.get("icon_img"):
                image_url = api.get("icon_img")

        return SocialProfile(
            url=public_url,
            username=username,
            network_name="reddit",
            existe=exists,
            metadata=metadata,
            bio=bio,
            imagen_url=image_url,
        )
