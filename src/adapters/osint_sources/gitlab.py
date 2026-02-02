"""Scanner OSINT: GitLab.

Implementación mínima:
- Verifica existencia mediante HTTP status al perfil público.
"""

from __future__ import annotations

from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class GitLabScanner(OSINTScanner):
    _base_url = "https://gitlab.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        import re
        url = f"{self._base_url}/{username}"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)

        exists = response.status_code == 200
        name = None
        if exists:
            # Extraer <title> del HTML
            html = response.text if hasattr(response, "text") else await response.aread()
            if not isinstance(html, str):
                html = html.decode(errors="ignore")
            m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if m:
                name = m.group(1).replace("· GitLab", "").strip(" ·-")
        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
            "name": name,
            "server": response.headers.get("server"),
        }
        return SocialProfile(
            url=str(response.url),
            username=username,
            network_name="gitlab",
            existe=exists,
            metadata=metadata,
        )
