"""Scanner OSINT: Gravatar profile JSON (email).

Consulta `https://en.gravatar.com/<md5>.json`.
- 200 => hay perfil público en Gravatar (puede incluir displayName, aboutMe, urls, etc.)
- 404 => no hay perfil público
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _email_md5(email: str) -> str:
    return hashlib.md5(email.encode("utf-8")).hexdigest()  # nosec - hash público requerido por Gravatar


class GravatarProfileScanner(OSINTScanner):
    _base_url = "https://en.gravatar.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        email = _normalize_email(username)
        h = _email_md5(email)

        url = f"{self._base_url}/{h}.json"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)

        exists = response.status_code == 200
        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
            "email_md5": h,
            "normalized_email": email,
        }

        bio: str | None = None
        image_url: str | None = None

        if exists:
            try:
                payload = json.loads(response.text)
                entry = None
                if isinstance(payload, dict):
                    arr = payload.get("entry")
                    if isinstance(arr, list) and arr:
                        entry = arr[0]
                if isinstance(entry, dict):
                    bio = entry.get("aboutMe") if isinstance(entry.get("aboutMe"), str) else None
                    thumb = entry.get("thumbnailUrl")
                    image_url = thumb if isinstance(thumb, str) else None
                    display = entry.get("displayName")
                    if isinstance(display, str):
                        metadata["display_name"] = display
                    preferred = entry.get("preferredUsername")
                    if isinstance(preferred, str):
                        metadata["preferred_username"] = preferred
                    urls = entry.get("urls")
                    if isinstance(urls, list):
                        metadata["urls"] = urls
            except Exception as exc:
                metadata["parse_error"] = str(exc)

        return SocialProfile(
            url=str(response.url),
            username=email,
            network_name="gravatar_profile",
            existe=exists,
            metadata=metadata,
            bio=bio,
            imagen_url=image_url,
        )
