"""Scanner OSINT: Gravatar (email).

Implementación:
- Normaliza el email (strip + lower).
- Calcula MD5 del email normalizado.
- Consulta el avatar con `d=404` para determinar existencia.

Notas:
- 200 => existe gravatar
- 404 => no existe gravatar
"""

from __future__ import annotations

import hashlib
from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class GravatarScanner(OSINTScanner):
    _base_url = "https://www.gravatar.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        email = _normalize_email(username)
        # Hash público (Gravatar requiere MD5 del email normalizado).
        email_md5 = hashlib.md5(email.encode("utf-8")).hexdigest()  # nosec - hash público

        # `d=404` hace que el recurso devuelva 404 si no existe.
        avatar_url = f"{self._base_url}/avatar/{email_md5}?s=200&d=404"

        async with build_async_client(self._settings) as client:
            response = await client.get(avatar_url)

        exists = response.status_code == 200
        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
            "email_md5": email_md5,
            "normalized_email": email,
        }

        return SocialProfile(
            url=str(response.url),
            username=email,
            network_name="gravatar",
            existe=exists,
            metadata=metadata,
            imagen_url=str(response.url) if exists else None,
        )
