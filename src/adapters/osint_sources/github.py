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

    async def scan(self, username: str) -> SocialProfile | list[SocialProfile]:
        public_url = f"{self._base_url}/{username}"

        # Inicializar listas antes de cualquier uso
        other_emails: list[str] = []
        other_users: list[str] = []
        other_websites: list[str] = []
        bio = None
        image_url = None

        api = await fetch_github_deep(username=username, settings=self._settings)
        exists = api is not None

        if api:
            if isinstance(api.get("bio"), str):
                bio = api.get("bio")
            if isinstance(api.get("avatar_url"), str):
                image_url = api.get("avatar_url")
            email = api.get("email")
            if isinstance(email, str):
                other_emails.append(email)
            blog = api.get("blog")
            if isinstance(blog, str) and blog.strip():
                other_websites.append(blog.strip())
            twitter_username = api.get("twitter_username")
            if isinstance(twitter_username, str) and twitter_username.strip():
                other_users.append(twitter_username.strip())

        # Construimos el metadata y aseguramos que los campos extra estén presentes
        metadata: dict[str, Any] = {
            "source": "github_api",
        }
        if api:
            metadata.update(api)
        if other_emails:
            metadata["other_emails"] = other_emails
        if other_users:
            metadata["other_users"] = other_users
        if other_websites:
            metadata["other_websites"] = other_websites

        # Creamos el perfil principal
        main_profile = SocialProfile(
            url=public_url,
            username=username,
            network_name="github",
            existe=exists,
            metadata=metadata,
            bio=bio,
            imagen_url=image_url,
        )

        # Creamos perfiles adicionales para que aparezcan en la tabla
        extra_profiles = []
        for email in other_emails:
            extra_profiles.append(SocialProfile(
                url="https://github.com/" + username,
                username=email,
                network_name="github_email",
                existe=True,
                metadata={"source": "github_api", "from_username": username},
            ))
        for user in other_users:
            extra_profiles.append(SocialProfile(
                url="https://github.com/" + user,
                username=user,
                network_name="github_user",
                existe=True,
                metadata={"source": "github_api", "from_username": username},
            ))

        # Retornamos todos los perfiles (el principal y los extras)
        if extra_profiles:
            return [main_profile] + extra_profiles
        return main_profile
