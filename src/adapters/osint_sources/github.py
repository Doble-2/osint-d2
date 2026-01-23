"""Scanner OSINT: GitHub.

Fase 2:
- Usa la API oficial de GitHub para extraer metadata (bio/location/etc.).
- Mantiene una URL canónica pública (`https://github.com/<user>`).
"""

from __future__ import annotations

from typing import Any

from adapters.specific_scrapers import fetch_github_deep
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class GitHubScanner(OSINTScanner):
    """Verifica la existencia de un username en GitHub."""

    _base_url = "https://github.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        public_url = f"{self._base_url}/{username}"

        api = await fetch_github_deep(username=username, settings=self._settings)
        exists = api is not None

        metadata: dict[str, Any] = {
            "source": "github_api",
        }
        if api:
            metadata.update(api)

        bio = None
        image_url = None
        if api:
            if isinstance(api.get("bio"), str):
                bio = api.get("bio")
            if isinstance(api.get("avatar_url"), str):
                image_url = api.get("avatar_url")

        return SocialProfile(
            url=public_url,
            username=username,
            network_name="github",
            existe=exists,
            metadata=metadata,
            bio=bio,
            imagen_url=image_url,
        )
