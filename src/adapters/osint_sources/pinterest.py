"""Scanner OSINT: Pinterest.

Implementación mínima:
- Verifica existencia mediante HTTP status.

Nota:
- Pinterest puede aplicar anti-bot; este es un check best-effort.
"""

from __future__ import annotations

from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class PinterestScanner(OSINTScanner):
    _base_url = "https://www.pinterest.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        url = f"{self._base_url}/{username}/"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)

        exists = response.status_code == 200
        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
        }

        return SocialProfile(
            url=str(response.url),
            username=username,
            network_name="pinterest",
            existe=exists,
            metadata=metadata,
        )
