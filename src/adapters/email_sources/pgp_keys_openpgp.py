"""Scanner OSINT: keys.openpgp.org (email).

Endpoint web de búsqueda:
- `https://keys.openpgp.org/search?q=<email>`

La página devuelve 200 tanto si hay resultados como si no.
Usamos heurística de contenido para marcar existencia.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class OpenPGPKeysScanner(OSINTScanner):
    _base_url = "https://keys.openpgp.org"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        email = username.strip().lower()
        url = f"{self._base_url}/search?q={quote(email)}"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)

        text = response.text or ""
        # Heurística: si no hay claves, suele aparecer un mensaje de "No results".
        not_found_markers = ["No results", "No keys found", "No matching keys"]
        found = response.status_code == 200 and not any(m in text for m in not_found_markers)

        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
            "heuristic": "content",
        }

        return SocialProfile(
            url=str(response.url),
            username=email,
            network_name="openpgp_keys",
            existe=found,
            metadata=metadata,
        )
