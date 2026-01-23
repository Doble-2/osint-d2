"""Scanner OSINT: Ubuntu keyserver (HKP) por email.

Busca en:
- `https://keyserver.ubuntu.com/pks/lookup?op=index&search=<email>`

Suele responder 200 siempre; determinamos existencia por contenido.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class UbuntuKeyserverScanner(OSINTScanner):
    _base_url = "https://keyserver.ubuntu.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        email = username.strip().lower()
        url = f"{self._base_url}/pks/lookup?op=index&search={quote(email)}"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)

        text = response.text or ""
        # Heurística: cuando no hay resultados suele aparecer "No results".
        found = response.status_code == 200 and "No results" not in text

        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
            "heuristic": "content",
        }

        return SocialProfile(
            url=str(response.url),
            username=email,
            network_name="ubuntu_keyserver",
            existe=found,
            metadata=metadata,
        )
